#!/usr/bin/env python3
"""Check the adapted Compass graph against the consumer contract.

Compass 0.4.2 does not ship a diagnose command and its native graph has no
label/source_file, so the contract is enforced here, before the OKF stage.
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


def resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else (REPO_ROOT / candidate).resolve()


def check(graph: dict, min_source_file_ratio: float, max_dangling: int) -> dict:
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if edges is None:
        edges = graph.get("links")
    failures = []
    if not isinstance(nodes, list) or not nodes:
        failures.append("graph has no nodes")
        nodes = []
    if not isinstance(edges, list):
        failures.append("graph has no edges/links list")
        edges = []

    ids = set()
    missing_id = 0
    missing_label = 0
    missing_source_file = 0
    for node in nodes:
        node_id = node.get("id")
        if node_id in (None, ""):
            missing_id += 1
        else:
            ids.add(node_id)
        if not str(node.get("label") or "").strip():
            missing_label += 1
        if not str(node.get("source_file") or "").strip():
            missing_source_file += 1

    bad_endpoints = 0
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            bad_endpoints += 1
        elif source not in ids or target not in ids:
            bad_endpoints += 1

    ratio = (len(nodes) - missing_source_file) / len(nodes) if nodes else 0.0
    if missing_id:
        failures.append(f"{missing_id} nodes without id")
    if missing_label:
        failures.append(f"{missing_label} nodes without label")
    if ratio < min_source_file_ratio:
        failures.append(
            f"source_file coverage {ratio:.2f} below threshold {min_source_file_ratio:.2f}"
        )
    if bad_endpoints > max_dangling:
        failures.append(f"{bad_endpoints} edges with missing or invalid endpoints")

    return {
        "ok": not failures,
        "nodes": len(nodes),
        "edges": len(edges),
        "missing_id": missing_id,
        "missing_label": missing_label,
        "missing_source_file": missing_source_file,
        "source_file_ratio": round(ratio, 4),
        "bad_endpoints": bad_endpoints,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--graph", help="graph to check (default: graph_json)")
    parser.add_argument("--report", help="report path (default: compass_graph_check.report)")
    parser.add_argument("--min-source-file-ratio", type=float)
    parser.add_argument("--max-dangling", type=int)
    args = parser.parse_args()

    config = json.loads(resolve(args.config).read_text(encoding="utf-8"))
    rules = config.get("compass_graph_check", {})
    graph_path = resolve(args.graph or config["graph_json"])
    report_path = resolve(args.report or rules.get("report", "compass-out/graph-check.json"))
    min_ratio = (
        args.min_source_file_ratio
        if args.min_source_file_ratio is not None
        else float(rules.get("min_source_file_ratio", 0.9))
    )
    max_dangling = (
        args.max_dangling if args.max_dangling is not None else int(rules.get("max_dangling", 0))
    )

    if not graph_path.is_file():
        print(f"error: graph not found: {graph_path}", file=sys.stderr)
        return 2
    result = check(json.loads(graph_path.read_text(encoding="utf-8")), min_ratio, max_dangling)
    result["graph"] = str(graph_path.relative_to(REPO_ROOT)) if graph_path.is_relative_to(REPO_ROOT) else str(graph_path)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(report_path.parent), prefix=f".{report_path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, report_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

    print(json.dumps(result, indent=2))
    if result["ok"]:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
