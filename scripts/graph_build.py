#!/usr/bin/env python3
"""Build/validate an LPG sidecar and seal a content-addressed artifact manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import lpg


def paths(config_path: Path) -> tuple[Path, dict]:
    return config_path.resolve().parent, json.loads(config_path.read_text(encoding='utf-8'))


def configured(root: Path, config: dict, key: str) -> Path:
    return lpg.safe_path(root, config[key])


def output_path(root: Path, config: dict, key: str) -> Path:
    path = configured(root, config, key)
    for name in config.get('immutable_roots', []):
        if path.is_relative_to(configured(root, {'root': name}, 'root')):
            raise ValueError(f'{key}: output inside immutable root')
    return path


def convert_legacy(data: dict, project: str, document: str) -> dict:
    """Lossless legacy payload retained; no unsupported extraction claims."""
    nodes, mapping = [], {}
    for node in data.get('nodes', []):
        local = str(node['id'])
        ident = lpg.identity(project, document, local)
        mapping[local] = ident
        nodes.append(dict(id=ident, project=project, document=document, local_id=local,
                          layer='knowledge', type='Concept', legacy=node))
    edges = []
    for original in data.get('edges', data.get('links', [])):
        edges.append(dict(id=lpg.digest(original), source=mapping.get(str(original.get('source')), 'missing'),
                          target=mapping.get(str(original.get('target')), 'missing'), type='RELATED_TO',
                          direction='out', status='inferred', provenance_incomplete=True,
                          source_document=None, source_section=None, source_hash=None,
                          extraction_method='legacy-import', legacy=original))
    return dict(schema_version=1, nodes=nodes, edges=edges, evidence=[], mappings=[],
                legacy_provenance='incomplete')


def finalize(data: dict) -> dict:
    # Build IDs do not depend on timestamps or previous build IDs.
    data = json.loads(json.dumps(data))
    data.pop('build_id', None)
    for edge in data.get('edges', []):
        edge.pop('build_id', None)
    for key in ('nodes', 'edges', 'evidence'):
        data[key] = sorted(data.get(key, []), key=lambda x: str(x.get('id')))
    data['mappings'] = sorted(data.get('mappings', []), key=lpg.digest)
    build_id = lpg.digest(data)
    data['build_id'] = build_id
    for edge in data['edges']:
        edge['build_id'] = build_id
    return data


def build(config_path: Path, input_path: Path | None = None) -> dict:
    root, config = paths(config_path)
    source = input_path or (configured(root, config, 'lpg_input') if config.get('lpg_input') else configured(root, config, 'graph_json'))
    data = json.loads(source.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1:
        data = convert_legacy(data, config['graph_retrieval']['project_id'],
                              source.resolve().relative_to(root).as_posix())
    graph = finalize(data)
    errors = lpg.validate(graph) + lpg.verify_evidence(root, graph)
    if errors:
        raise ValueError('\n'.join(errors))
    verify_mappings(root, config, graph)
    lpg.atomic_json(output_path(root, config, 'lpg_json'), graph)
    return graph


def verify_mappings(root: Path, config: dict, graph: dict) -> None:
    # Verify explicit mappings against actual index IDs, including partitioned indexes.
    import graph_retrieval
    items = graph_retrieval.query_index.load_index(configured(root, config, 'semantic_index'))['items']
    chunks = {str(x['id']): x for x in items}
    for m in graph['mappings']:
        item = chunks.get(m['chunk_id'])
        if not item or item['sourcePath'] != m['note_path']:
            raise ValueError(f"mapping: index chunk missing/mismatched {m['chunk_id']}")
        lpg.safe_path(configured(root, config, 'bundle_root'), m['note_path'])


def snapshots(root: Path, config: dict) -> dict:
    root = root.resolve()
    files = {}
    source_names = []
    for name in config.get('source_roots', []):
        directory = lpg.safe_path(root, name)
        if directory.is_dir():
            source_names.extend(p for p in directory.rglob('*') if p.is_file() and p.name not in config.get('source_ignored_files', []))
    bundle = configured(root, config, 'bundle_root')
    wiki = sorted(p for p in bundle.rglob('*.md') if p.is_file())
    index_file = configured(root, config, 'semantic_index')
    if index_file.is_file():
        indexes = [index_file]
    else:
        manifest = index_file.parent / 'manifest.json'
        data = json.loads(manifest.read_text(encoding='utf-8'))
        indexes = [manifest] + [lpg.safe_path(index_file.parent / 'parts', part['name']) for part in data['parts']]
    graph = json.loads(configured(root, config, 'lpg_json').read_text(encoding='utf-8'))
    evidence_files = [lpg.safe_path(root, ev['document']) for ev in graph['evidence']]
    evidence_files += [lpg.safe_path(root, ev['note_path']) for ev in graph['evidence'] if ev.get('note_path')]
    if config.get('lpg_input'):
        evidence_files.append(configured(root, config, 'lpg_input'))
    for path in sorted(set(source_names + wiki + indexes + evidence_files + [configured(root, config, 'graph_json'), configured(root, config, 'lpg_json')])):
        if not path.resolve().is_relative_to(root):
            raise ValueError(f'artifact outside repository: {path}')
        files[path.relative_to(root).as_posix()] = lpg.file_hash(path)
    if not wiki:
        raise ValueError('wiki missing or empty')
    # Config changes affecting retrieval/chunking must invalidate the seal too.
    return dict(files=files, config_hash=lpg.digest(config))


def seal(config_path: Path) -> dict:
    root, config = paths(config_path)
    graph = json.loads(configured(root, config, 'lpg_json').read_text(encoding='utf-8'))
    errors = lpg.validate(graph) + lpg.verify_evidence(root, graph)
    if errors:
        raise ValueError('\n'.join(errors))
    verify_mappings(root, config, graph)
    snapshot = snapshots(root, config)
    manifest = dict(schema_version=1, graph_schema_version=1, graph_build_id=graph['build_id'],
                    build_id=lpg.digest(snapshot), **snapshot)
    lpg.atomic_json(output_path(root, config, 'build_manifest'), manifest)
    return manifest


def check_manifest(root: Path, config: dict, graph: dict) -> list[str]:
    try:
        manifest = json.loads(configured(root, config, 'build_manifest').read_text(encoding='utf-8'))
        snapshot = snapshots(root, config)
        if (manifest.get('schema_version') != 1 or manifest.get('graph_schema_version') != 1
                or manifest.get('graph_build_id') != graph['build_id']
                or manifest.get('build_id') != lpg.digest(snapshot)
                or manifest.get('files') != snapshot['files']
                or manifest.get('config_hash') != snapshot['config_hash']):
            return ['manifest: artifact/input/config hashes or build IDs mismatch']
        return []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f'manifest: {exc}']


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'seal', 'validate'])
    parser.add_argument('--config', type=Path, default=Path('knowledge-config.json'))
    parser.add_argument('--input', type=Path, help='explicit LPG envelope; otherwise import configured Graphify JSON')
    args = parser.parse_args()
    try:
        if args.action == 'build':
            result = build(args.config, args.input)
        elif args.action == 'seal':
            result = seal(args.config)
        else:
            root, config = paths(args.config)
            result = json.loads(configured(root, config, 'lpg_json').read_text(encoding='utf-8'))
            errors = lpg.validate(result)
            if not errors:
                errors += lpg.verify_evidence(root, result) + check_manifest(root, config, result)
            if errors:
                raise ValueError('\n'.join(errors))
        print(json.dumps({'status': 'ok', 'build_id': result['build_id']}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
