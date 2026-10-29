#!/usr/bin/env python3
"""Adapt a Compass graph.json to the shape consumed by cag_context.py.

Compass nodes carry name/qualifiedName and source.file; the consumers expect
label and source_file. The raw graph is never rewritten: the adapter writes a
separate file and the config points graph_json at it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "knowledge-config.compass.json"


def adapt(graph: dict) -> dict:
    nodes = graph.get("nodes") or []
    links = graph.get("links") or graph.get("edges") or []
    adapted_nodes = []
    for node in nodes:
        source = node.get("source") or {}
        item = dict(node)
        item["label"] = (
            node.get("label")
            or node.get("name")
            or node.get("qualifiedName")
            or str(node.get("id", ""))
        )
        item["source_file"] = node.get("source_file") or source.get("file") or ""
        item["type"] = node.get("type") or node.get("kind") or ""
        adapted_nodes.append(item)
    adapted_nodes.sort(key=lambda item: str(item.get("id", "")))

    adapted_edges = []
    for edge in links:
        item = dict(edge)
        item["type"] = edge.get("type") or edge.get("kind") or "related"
        adapted_edges.append(item)
    adapted_edges.sort(
        key=lambda item: (
            str(item.get("source", "")),
            str(item.get("target", "")),
            str(item.get("type", "")),
        )
    )

    return {
        "directed": bool(graph.get("directed", True)),
        "nodes": adapted_nodes,
        "edges": adapted_edges,
        "meta": {"generator": "compass_graph_adapter", "source": "compass graph.json"},
    }


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else (REPO_ROOT / candidate).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--input", help="raw compass graph (default: compass_graph_json)")
    parser.add_argument("--output", help="adapted graph (default: graph_json)")
    args = parser.parse_args()

    config_path = resolve(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source = resolve(args.input or config["compass_graph_json"])
    target = resolve(args.output or config["graph_json"])

    if not source.is_file():
        print(f"error: input graph not found: {source}", file=sys.stderr)
        return 2
    graph = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(graph.get("nodes"), list) or not graph["nodes"]:
        print(f"error: input graph has no nodes: {source}", file=sys.stderr)
        return 1

    payload = adapt(graph)
    write_atomic(target, payload)
    stats = {
        "input": str(source.relative_to(REPO_ROOT)) if source.is_relative_to(REPO_ROOT) else str(source),
        "output": str(target.relative_to(REPO_ROOT)) if target.is_relative_to(REPO_ROOT) else str(target),
        "nodes": len(payload["nodes"]),
        "edges": len(payload["edges"]),
        "missing_label": sum(1 for node in payload["nodes"] if not node["label"]),
        "missing_source_file": sum(1 for node in payload["nodes"] if not node["source_file"]),
    }
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
