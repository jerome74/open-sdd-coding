"""Versioned file LPG contract. No inferred identity merging, no SDD state."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import quote

VERSION = 1
KNOWLEDGE = {'Concept', 'Actor', 'Process', 'Rule', 'Document', 'Evidence'}
SDD = {'Requirement', 'Specification', 'Criterion', 'CapabilityBinding', 'Plan',
       'Artifact', 'Validation', 'Publication'}
# Directed endpoint contracts; None means any type in the same logical layer.
RELATIONS = {
    'RELATED_TO': (None, None), 'DEPENDS_ON': (None, None),
    'CONSTRAINS': ({'Rule'}, {'Concept', 'Actor', 'Process', 'Document'}),
    'EXCEPTION_TO': ({'Rule'}, {'Rule'}), 'CONTRADICTS': ({'Rule'}, {'Rule'}),
    'DOCUMENTS': ({'Document'}, KNOWLEDGE), 'SUPPORTS': ({'Evidence'}, KNOWLEDGE),
    'SPECIFIED_BY': ({'Requirement'}, {'Specification'}),
    'HAS_CRITERION': ({'Requirement', 'Specification'}, {'Criterion'}),
    'VERIFIED_BY': ({'Criterion'}, {'Validation'}),
    'IMPLEMENTS': ({'Artifact'}, {'Specification', 'Requirement'}),
    'BINDS': ({'Plan', 'Specification'}, {'CapabilityBinding'}),
    'PRODUCES': ({'Plan', 'CapabilityBinding'}, {'Artifact'}),
    'PUBLISHED_AS': ({'Artifact'}, {'Publication'}),
}
STATES = {'explicit', 'inferred', 'confirmed', 'disputed'}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(project: str, document: str, local_id: str) -> str:
    if not all(isinstance(x, str) and x.strip() for x in (project, document, local_id)):
        raise ValueError('identity: project, document and local_id required')
    return ':'.join(quote(x, safe='') for x in (project, document, local_id))


def safe_path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError(f'path must be relative: {name!r}')
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'path escapes root: {name}')
    return path


def _validate(graph: dict) -> list[str]:
    """Return all deterministic diagnostics; malformed external data never raises."""
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ['graph: object required']
    if graph.get('schema_version') != VERSION:
        errors.append('schema_version: expected 1')
    if not isinstance(graph.get('build_id'), str) or not graph.get('build_id'):
        errors.append('build_id: required')
    collections = {}
    for key in ('nodes', 'edges', 'evidence', 'mappings'):
        items = graph.get(key)
        if not isinstance(items, list) or any(not isinstance(x, dict) for x in items):
            errors.append(f'{key}: array of objects required')
            items = []
        collections[key] = items
    nodes, evidence = {}, {}
    for key, target in (('nodes', nodes), ('evidence', evidence)):
        for obj in collections[key]:
            ident = obj.get('id')
            if not isinstance(ident, str) or not ident:
                errors.append(f'{key}: nonempty id required')
                continue
            if ident in target:
                errors.append(f'{key}: duplicate id {ident}')
            target[ident] = obj
    for ident, node in nodes.items():
        try:
            expected = identity(node.get('project'), node.get('document'), node.get('local_id'))
            if ident != expected:
                errors.append(f'{ident}: identity collision/unqualified id')
        except ValueError as exc:
            errors.append(f'{ident}: {exc}')
        layer = node.get('layer')
        if node.get('type') not in (KNOWLEDGE if layer == 'knowledge' else SDD if layer == 'sdd' else set()):
            errors.append(f'{ident}: invalid layer/type')
        if not isinstance(node.get('aliases', []), list):
            errors.append(f'{ident}: aliases must be a list; aliases never merge identities')
    for ident, ev in evidence.items():
        for field in ('document', 'section', 'passage', 'source_hash'):
            if not isinstance(ev.get(field), str) or not ev.get(field):
                errors.append(f'{ident}: evidence {field} required')
        if ev.get('note_path') is not None:
            if not isinstance(ev['note_path'], str) or not ev['note_path'] or not isinstance(ev.get('note_hash'), str) or len(ev.get('note_hash', '')) != 64:
                errors.append(f'{ident}: wiki replica requires note_path and note_hash')
        h = ev.get('source_hash', '')
        if not isinstance(h, str) or len(h) != 64 or any(c not in '0123456789abcdef' for c in h):
            errors.append(f'{ident}: source_hash must be SHA256')
    seen, triples = set(), set()
    for edge in collections['edges']:
        eid = edge.get('id')
        if not isinstance(eid, str) or not eid or eid in seen:
            errors.append(f'edge: missing/duplicate id {eid}')
        seen.add(str(eid))
        source, target = nodes.get(str(edge.get('source'))), nodes.get(str(edge.get('target')))
        if not source or not target:
            errors.append(f'{eid}: orphan endpoint')
        relation = edge.get('type')
        if relation not in RELATIONS:
            errors.append(f'{eid}: invalid relation type {relation}')
        elif source and target:
            left, right = RELATIONS[relation]
            if source['layer'] != target['layer'] or (left and source['type'] not in left) or (right and target['type'] not in right):
                errors.append(f'{eid}: disallowed endpoint types/layers')
        triple = (str(edge.get('source')), str(edge.get('target')), str(relation))
        if triple in triples:
            errors.append(f'{eid}: duplicate relation')
        triples.add(triple)
        if edge.get('direction') != 'out':
            errors.append(f'{eid}: direction must be out (source → target)')
        if edge.get('status') not in STATES:
            errors.append(f'{eid}: invalid status')
        if edge.get('build_id') != graph.get('build_id'):
            errors.append(f'{eid}: build_id mismatch')
        if edge.get('status') == 'confirmed' and not edge.get('human_confirmation'):
            errors.append(f'{eid}: confirmed requires human_confirmation')
        confidence = edge.get('model_confidence')
        if confidence is not None and (not isinstance(confidence, (float, int)) or not 0 <= confidence <= 1):
            errors.append(f'{eid}: invalid model_confidence')
        if edge.get('provenance_incomplete') is True:
            if edge.get('status') != 'inferred':
                errors.append(f'{eid}: incomplete legacy provenance must be inferred')
            continue
        ev = evidence.get(str(edge.get('evidence_id')))
        if not ev:
            errors.append(f'{eid}: missing evidence')
        for field in ('source_document', 'source_section', 'source_hash', 'extraction_method'):
            if not isinstance(edge.get(field), str) or not edge.get(field):
                errors.append(f'{eid}: provenance {field} required')
        if ev and any(edge.get(a) != ev.get(b) for a, b in
                      [('source_document', 'document'), ('source_section', 'section'), ('source_hash', 'source_hash')]):
            errors.append(f'{eid}: evidence provenance mismatch')
    seen_maps = set()
    for mapping in collections['mappings']:
        if mapping.get('entity_id') not in nodes or mapping.get('evidence_id') not in evidence:
            errors.append('mapping: orphan entity/evidence')
        if not all(isinstance(mapping.get(k), str) and mapping.get(k) for k in ('note_path', 'chunk_id')):
            errors.append('mapping: note_path and chunk_id required')
        key = digest(mapping)
        if key in seen_maps:
            errors.append('mapping: duplicate')
        seen_maps.add(key)
    return sorted(errors)


def validate(graph: dict) -> list[str]:
    try:
        return _validate(graph)
    except (TypeError, KeyError, AttributeError, ValueError) as exc:
        return [f'schema: malformed field type or missing property: {exc}']


def verify_evidence(root: Path, graph: dict) -> list[str]:
    errors = []
    for ev in graph['evidence']:
        try:
            path = safe_path(root, ev['document'])
            if file_hash(path) != ev['source_hash']:
                errors.append(f"{ev['id']}: source hash changed")
            if ev['passage'] not in path.read_text(encoding='utf-8'):
                errors.append(f"{ev['id']}: passage missing from source")
            if ev.get('note_path'):
                replica = safe_path(root, ev['note_path'])
                if file_hash(replica) != ev['note_hash'] or ev['passage'] not in replica.read_text(encoding='utf-8'):
                    errors.append(f"{ev['id']}: wiki replica hash/passage mismatch")
        except (OSError, ValueError, UnicodeError) as exc:
            errors.append(f"{ev['id']}: {exc}")
    return errors


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    temporary.replace(path)
