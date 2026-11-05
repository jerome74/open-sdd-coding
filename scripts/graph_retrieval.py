#!/usr/bin/env python3
"""Semantic-first bounded typed graph retrieval; deterministic and read-only."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import graph_build
import lpg

SKILL_SCRIPTS = Path(__file__).resolve().parents[1] / '.opencode/skills/wiki-semantic-search/scripts'
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))
import query_index  # noqa: E402


def cost(value: object) -> int:
    """Conservative UTF-8 byte bound, not a model-specific token estimate."""
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())


def retrieve(*, config_path: Path, query: str, top_k: int | None = None,
             max_hops: int = 1, relation_types: list[str] | None = None,
             direction: str = 'out', max_nodes: int = 40, max_edges: int = 60,
             max_tokens: int = 4000, timeout_ms: int = 2000, runner: object | None = None,
             graph_path: Path | None = None, bundle_root: Path | None = None) -> dict:
    if not isinstance(query, str) or not query.strip():
        raise ValueError('query: nonempty string required')
    for name, value, low, high in [('top_k', top_k if top_k is not None else 5, 1, 100),
                                    ('max_hops', max_hops, 0, 2), ('max_nodes', max_nodes, 1, 1000),
                                    ('max_edges', max_edges, 0, 2000), ('max_tokens', max_tokens, 2, 100000),
                                    ('timeout_ms', timeout_ms, 1, 60000)]:
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'{name}: integer in [{low}, {high}] required')
    if direction not in ('out', 'in', 'both'):
        raise ValueError('direction: out/in/both required')
    if relation_types is not None and (not isinstance(relation_types, list) or any(x not in lpg.RELATIONS for x in relation_types)):
        raise ValueError('relation_types: unknown relation')
    root, config = graph_build.paths(config_path)
    if top_k is None:
        top_k = int(config.get('search', {}).get('top_k', 5))
        if not 1 <= top_k <= 100:
            raise ValueError('configured top_k: integer in [1, 100] required')
    started = time.perf_counter()
    result = dict(query=query, status='runtime_error', semantic_status='runtime_error',
                  graph_status='graph_missing', diagnostics=[], notes=[], relations=[],
                  node_paths=[], context=[], budget_unit='utf8_bytes_upper_bound', context_cost=2)
    index_file = graph_build.configured(root, config, 'semantic_index')
    try:
        if not index_file.is_file() and not (index_file.parent / 'manifest.json').is_file():
            result['status'] = result['semantic_status'] = 'index_missing'
            result['diagnostics'].append(f'index_missing: {index_file}')
            return result
        search = query_index.search(config_path=config_path, query=query, top_k=top_k, runner=runner)
        result['esito'] = search['esito']
        semantic_status = {'conRisultati': 'ok', 'nessunRisultato': 'no_results'}.get(search['esito'], 'runtime_error')
        result['status'] = result['semantic_status'] = semantic_status
        if search.get('error'):
            result['diagnostics'].append(search['error'])
        # Keep direct hits ahead of adjacent-chunk expansion, with deterministic ties.
        notes = sorted(search['results'], key=lambda x: (bool(x.get('expanded')), -x['score'], str(x.get('sourcePath')), x.get('chunkIndex', 0)))
        packed = result['context']
        seen_notes = set()
        for note in notes:
            note_key = (note.get('sourcePath'), note.get('chunkIndex'))
            if note_key in seen_notes:
                continue
            seen_notes.add(note_key)
            entry = dict(kind='semantic', **note)
            if cost(packed + [entry]) > max_tokens:
                text = str(entry.get('rawText') or '')
                low, high = 0, len(text)
                entry['truncated'] = True
                while low < high:
                    middle = (low + high + 1) // 2
                    entry['rawText'] = text[:middle]
                    if cost(packed + [entry]) <= max_tokens:
                        low = middle
                    else:
                        high = middle - 1
                entry['rawText'] = text[:low]
                if not low or cost(packed + [entry]) > max_tokens:
                    result['diagnostics'].append('token_budget: semantic context omitted')
                    continue
            packed.append(entry)
            result['notes'].append({k: v for k, v in entry.items() if k != 'kind'})
        graph_file = graph_path or (graph_build.configured(root, config, 'lpg_json') if 'lpg_json' in config else None)
        if graph_file is None or not graph_file.is_file():
            result['diagnostics'].append('graph_missing: semantic fallback; build LPG sidecar')
            return result
        try:
            graph = json.loads(graph_file.read_text(encoding='utf-8'))
            errors = lpg.validate(graph)
            if errors:
                result['graph_status'] = 'invalid_graph'
                result['diagnostics'].extend(errors)
                return result
        except (ValueError, KeyError, TypeError) as exc:
            result['graph_status'] = 'invalid_graph'
            result['diagnostics'].append(str(exc))
            return result
        errors = graph_build.check_manifest(root, config, graph)
        if errors:
            result['graph_status'] = 'stale_artifacts'
            result['diagnostics'].extend(errors)
            return result
        bundle_for_evidence = (bundle_root or graph_build.configured(root, config, 'bundle_root')).resolve()
        # Verify the quoted wiki replica only. The manifest checks authoritative source hashes;
        # query-time code never reads raw source passages.
        errors = []
        for ev in graph['evidence']:
            replica = lpg.safe_path(root, ev.get('note_path') or ev['document'])
            if not replica.is_relative_to(bundle_for_evidence):
                continue
            expected_hash = ev.get('note_hash') if ev.get('note_path') else ev['source_hash']
            if lpg.file_hash(replica) != expected_hash or ev['passage'] not in replica.read_text(encoding='utf-8'):
                errors.append(f"{ev['id']}: wiki evidence hash/passage mismatch")
        if errors:
            result['graph_status'] = 'stale_artifacts'
            result['diagnostics'].extend(errors)
            return result
        result['graph_status'] = 'ok'
        if graph.get('legacy_provenance'):
            result['diagnostics'].append('legacy provenance incomplete; relations excluded')
        items = query_index.load_index(index_file)['items']
        chunks = {(x['sourcePath'], x['chunkIndex']): str(x['id']) for x in items}
        selected = {chunks.get((x['sourcePath'], x['chunkIndex'])) for x in result['notes']}
        mappings = graph['mappings']
        # Explicit chunk-ID and exact note path join only.
        selected_pairs = {(x['sourcePath'], chunks.get((x['sourcePath'], x['chunkIndex']))) for x in result['notes']}
        seeds = sorted({m['entity_id'] for m in mappings if (m['note_path'], m['chunk_id']) in selected_pairs and m['chunk_id'] in selected})[:max_nodes]
        evidence = {x['id']: x for x in graph['evidence']}
        allowed = set(lpg.RELATIONS if relation_types is None else relation_types)
        edges = sorted(graph['edges'], key=lambda e: e['id'])
        visited, seen_edges = set(seeds), set()
        frontier = [(seed, [seed]) for seed in seeds]
        result['node_paths'] = [p for _, p in frontier]
        deadline = time.perf_counter() + timeout_ms / 1000
        for _ in range(max_hops):
            next_frontier = []
            for node, path in frontier:
                for edge in edges:
                    if time.perf_counter() > deadline:
                        result['diagnostics'].append('traversal_timeout: partial context')
                        return result
                    if len(seen_edges) >= max_edges:
                        return result
                    if edge['id'] in seen_edges or edge['type'] not in allowed or edge.get('provenance_incomplete'):
                        continue
                    neighbour = None
                    if direction in ('out', 'both') and edge['source'] == node:
                        neighbour = edge['target']
                    elif direction in ('in', 'both') and edge['target'] == node:
                        neighbour = edge['source']
                    if neighbour is None or neighbour in path:
                        continue
                    if neighbour not in visited and len(visited) >= max_nodes:
                        continue
                    ev = evidence[edge['evidence_id']]
                    # Evidence for relational claims comes only from the wiki; no raw reads at query time.
                    document = lpg.safe_path(root, ev.get('note_path') or ev['document'])
                    bundle = (bundle_root or graph_build.configured(root, config, 'bundle_root')).resolve()
                    if not document.is_relative_to(bundle):
                        result['diagnostics'].append(f"{edge['id']}: evidence outside wiki; relation omitted")
                        continue
                    entry = dict(kind='relation', edge=edge, path=path + [neighbour], evidence=ev,
                                 citation=f"{ev['document']}#{ev['section']}")
                    if cost(packed + [entry]) > max_tokens:
                        result['diagnostics'].append('token_budget: graph expansion stopped')
                        return result
                    packed.append(entry)
                    result['relations'].append(entry)
                    seen_edges.add(edge['id'])
                    if neighbour not in visited:
                        visited.add(neighbour)
                        next_frontier.append((neighbour, path + [neighbour]))
                        result['node_paths'].append(path + [neighbour])
            frontier = next_frontier
        return result
    except (OSError, ValueError, KeyError, TypeError, query_index.build_index.IndexBuildError) as exc:
        result['diagnostics'].append(f'runtime_error: {exc}')
        if result['semantic_status'] == 'ok':
            result['graph_status'] = 'runtime_error'
        else:
            result['status'] = result['semantic_status'] = 'runtime_error'
        return result
    finally:
        result['context_cost'] = cost(result['context'])
        result['elapsed_ms'] = round((time.perf_counter() - started) * 1000, 3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query')
    parser.add_argument('--config', type=Path, default=Path('knowledge-config.json'))
    parser.add_argument('--top', type=int)
    parser.add_argument('--max-hops', type=int)
    parser.add_argument('--direction', choices=['out', 'in', 'both'], default=None)
    parser.add_argument('--relation-type', action='append', dest='relation_types')
    parser.add_argument('--max-nodes', type=int)
    parser.add_argument('--max-edges', type=int)
    parser.add_argument('--max-tokens', type=int)
    parser.add_argument('--timeout-ms', type=int)
    args = vars(parser.parse_args())
    args['config_path'] = args.pop('config')
    args['top_k'] = args.pop('top')
    try:
        _, config = graph_build.paths(args['config_path'])
        defaults = dict(max_hops=1, direction='out', max_nodes=40, max_edges=60, max_tokens=4000, timeout_ms=2000)
        for key, default in defaults.items():
            if args[key] is None:
                args[key] = config.get('graph_retrieval', {}).get(key, default)
        if args['relation_types'] is None:
            args['relation_types'] = config.get('graph_retrieval', {}).get('relation_types')
        result = retrieve(**args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'invalid_parameters', 'error': str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['status'] in ('runtime_error', 'index_missing') else 0


if __name__ == '__main__':
    raise SystemExit(main())
