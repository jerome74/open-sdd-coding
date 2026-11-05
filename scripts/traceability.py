#!/usr/bin/env python3
"""Read-only selective SDD projection from explicit structured Markdown references."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import graph_build
import lpg

MARKER = re.compile(r'<!-- sdd-(node|edge) (\{[^\n]*\}) -->')
ROLES = {
    'frd': {'Requirement', 'Criterion'}, 'specification': {'Specification', 'Criterion'},
    'binding': {'CapabilityBinding'}, 'plan': {'Plan', 'CapabilityBinding'},
    'artifact': {'Artifact'}, 'validation': {'Validation'}, 'publication': {'Publication'},
}


def ingest(root: Path, selection: dict) -> dict:
    """Read only named files; comments are authored references, never inferred by text matching."""
    project = selection['project_id']
    documents = selection['documents']
    if not isinstance(documents, list) or not documents:
        raise ValueError('documents: nonempty explicit selection required')
    nodes, edges, evidence = [], [], []
    seen = set()
    for entry in documents:
        name, role = entry['path'], entry['role']
        if name in seen or role not in ROLES:
            raise ValueError(f'duplicate document or invalid role: {name}, {role}')
        seen.add(name)
        path = lpg.safe_path(root, name)
        if path.suffix.lower() != '.md':
            raise ValueError(f'{name}: explicit Markdown record required (artifact may reference code in properties)')
        text, source_hash = path.read_text(encoding='utf-8'), lpg.file_hash(path)
        for match in MARKER.finditer(text):
            kind, content = match.groups()
            record = json.loads(content)
            if kind == 'node':
                if record['type'] not in ROLES[role]:
                    raise ValueError(f"{name}: node type {record['type']} disallowed for {role}")
                local_id = record['local_id']
                nodes.append(dict(id=lpg.identity(project, name, local_id), project=project,
                                  document=name, local_id=local_id, type=record['type'], layer='sdd',
                                  source_hash=source_hash, properties=record.get('properties', {})))
            else:
                target_doc = record['target_document']
                # References outside the explicit selection remain visible as orphan endpoints.
                lpg.safe_path(root, target_doc)
                source = lpg.identity(project, name, record['source_id'])
                target = lpg.identity(project, target_doc, record['target_id'])
                passage = match.group(0)
                eid = lpg.digest([name, passage])
                evidence.append(dict(id=eid, document=name, section=f'line-{text[:match.start()].count(chr(10)) + 1}',
                                     passage=passage, source_hash=source_hash))
                ev = evidence[-1]
                edges.append(dict(id=lpg.digest([source, target, record['type'], eid]), source=source,
                                  target=target, type=record['type'], direction='out',
                                  status=record.get('status', 'explicit'), evidence_id=eid,
                                  source_document=name, source_section=ev['section'], source_hash=source_hash,
                                  extraction_method='explicit-reference', target_hash=record.get('target_hash'),
                                  human_confirmation=record.get('human_confirmation')))
    return graph_build.finalize(dict(schema_version=1, nodes=nodes, edges=edges, evidence=evidence, mappings=[]))


def analyze(root: Path, graph: dict) -> dict:
    """Coverage denotes explicit links, never successful validation/completion."""
    errors = lpg.validate(graph)
    source_errors = lpg.verify_evidence(root, graph)
    for node in graph['nodes']:
        try:
            if lpg.file_hash(lpg.safe_path(root, node['document'])) != node.get('source_hash'):
                source_errors.append(f"{node['id']}: node source hash changed")
        except (OSError, ValueError) as exc:
            source_errors.append(f"{node['id']}: {exc}")
    nodes = {n['id']: n for n in graph['nodes']}
    orphans = [dict(edge_id=e['id'], source=e['source'], target=e['target'],
                    evidence_id=e.get('evidence_id'), reason='endpoint outside selected nodes')
               for e in graph['edges'] if e['source'] not in nodes or e['target'] not in nodes]
    result = dict(read_only=True, authority='constitution ## Roadmap', diagnostics=errors + source_errors,
                  orphan_references=orphans, uncovered_requirements=[], unverified_criteria=[],
                  changed_spec_artifacts=[], cross_document_dependencies=[], unknown_target_versions=[],
                  coverage_available=not errors and not source_errors)
    if errors or source_errors:
        return result
    # Confirmed confidence alone is not sufficient: validate() requires human confirmation.
    accepted = [e for e in graph['edges'] if e['status'] in ('explicit', 'confirmed')
                and e.get('extraction_method') == 'explicit-reference' and not e.get('provenance_incomplete')]
    for n in sorted(nodes.values(), key=lambda x: x['id']):
        if n['type'] == 'Requirement' and not any(e['source'] == n['id'] and e['type'] == 'SPECIFIED_BY' for e in accepted):
            result['uncovered_requirements'].append(dict(id=n['id'], document=n['document'], reason='no explicit validated SPECIFIED_BY reference'))
        if n['type'] == 'Criterion' and not any(e['source'] == n['id'] and e['type'] == 'VERIFIED_BY' for e in accepted):
            result['unverified_criteria'].append(dict(id=n['id'], document=n['document'], reason='no explicit validated VERIFIED_BY reference; no verdict on test execution'))
    for edge in sorted(accepted, key=lambda x: x['id']):
        source, target = nodes[edge['source']], nodes[edge['target']]
        detail = dict(edge_id=edge['id'], source=source['id'], target=target['id'],
                      evidence=next(ev for ev in graph['evidence'] if ev['id'] == edge['evidence_id']))
        if edge['type'] == 'DEPENDS_ON' and source['document'] != target['document']:
            result['cross_document_dependencies'].append(detail)
        if edge['type'] == 'IMPLEMENTS' and target['type'] == 'Specification':
            if not edge.get('target_hash'):
                result['unknown_target_versions'].append(dict(**detail, reason='target_hash not pinned; impact unknown'))
            elif lpg.file_hash(lpg.safe_path(root, target['document'])) != edge['target_hash']:
                result['changed_spec_artifacts'].append(dict(**detail, reason='specification hash differs from pinned target_hash'))
    return result


def run(config_path: Path, input_path: Path | None = None, fixture_mode: bool = False) -> dict:
    root, config = graph_build.paths(config_path)
    tc = config['traceability']
    missing = [key for key in ('constitution', 'capability_registry') if not lpg.safe_path(root, tc[key]).is_file()]
    if missing and not fixture_mode:
        return dict(status='not_initialized', missing=missing, read_only=True,
                    reason='Run /init-new-project before analyzing real SDD state')
    selection_path = input_path or lpg.safe_path(root, tc['input'])
    selection = json.loads(selection_path.read_text(encoding='utf-8'))
    graph = ingest(root, selection)
    return dict(status='fixture' if fixture_mode else 'ok', **analyze(root, graph))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('knowledge-config.json'))
    parser.add_argument('--input', type=Path)
    parser.add_argument('--fixture', action='store_true', help='explicit synthetic/uninitialized analysis; no real SDD attestation')
    args = parser.parse_args()
    try:
        result = run(args.config, args.input, args.fixture)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('coverage_available', False) else 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'invalid_input', 'error': str(exc), 'read_only': True}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
