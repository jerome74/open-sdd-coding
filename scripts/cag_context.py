#!/usr/bin/env python3
"""CAG Context Assembler — build the assistant's grounding context (FR-010, FR-011).

Given a question, it runs the semantic search (spec 02/04), then decides how to attach the
knowledge graph (`graph_json` from `knowledge-config.json`, produced by `graphify`):

- graph **<= threshold** (`cag.graph_threshold_kb`, default 100 KB) → the **whole** graph;
- graph **> threshold** → only the **sub-graph** connected to the found notes;
- graph **missing**, **older than the wiki**, or **unreadable** → semantic results only + a warning.

It records the FR-011 signals (`kb_consulted`, `note_citate`, `graph_used`) and appends one entry to
the **local** search log (spec 06). It performs no generation and no network call.

Usage
    python3 scripts/cag_context.py "<question>" [--top K] [--config PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# The retrieval engine lives in the wiki-semantic-search skill's scripts dir; reuse it read-only.
SKILL_SCRIPTS = REPO_ROOT / ".opencode" / "skills" / "wiki-semantic-search" / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))
import query_index  # noqa: E402

import search_log  # noqa: E402  (sibling logger, local only)

DEFAULT_CONFIG = "knowledge-config.json"
DEFAULT_GRAPH_THRESHOLD_KB = 100
DEFAULT_LOG_PATH = "logs/search-log.jsonl"


class CagError(Exception):
    """Fatal condition (e.g. missing graph_json key in config)."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config(config_path: Path) -> dict:
    return query_index.build_index.load_config(config_path)


def load_graph(graph_path: Path) -> tuple[list[dict], list[dict]]:
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = data.get("nodes") or []
    edges = data.get("edges") or data.get("links") or []
    return nodes, edges


def graph_is_stale(graph_path: Path, bundle_root: Path) -> bool:
    """The graph is stale when it predates the newest note in the wiki bundle."""
    if not bundle_root.is_dir():
        return False
    newest = max((path.stat().st_mtime for path in bundle_root.rglob("*.md")), default=0.0)
    return graph_path.stat().st_mtime < newest


def select_subgraph(nodes: list[dict], edges: list[dict], notes: list[dict]) -> tuple[list[dict], list[dict]]:
    """Keep the nodes connected to the found notes (by title/stem) plus their incident edges."""
    keys: set[str] = set()
    for note in notes:
        title = str(note.get("docTitle") or "").strip().lower()
        stem = Path(str(note.get("sourcePath") or "")).stem.strip().lower()
        if title:
            keys.add(title)
        if stem:
            keys.add(stem)
    if not keys:
        return [], []

    def matches(node: dict) -> bool:
        label = str(node.get("label", "")).lower()
        source = str(node.get("source_file", "")).lower()
        return any(key in label or key in source for key in keys)

    selected_ids = {node.get("id") for node in nodes if matches(node)}
    sub_edges = [edge for edge in edges if edge.get("source") in selected_ids or edge.get("target") in selected_ids]
    connected_ids = set(selected_ids)
    for edge in sub_edges:
        connected_ids.add(edge.get("source"))
        connected_ids.add(edge.get("target"))
    sub_nodes = [node for node in nodes if node.get("id") in connected_ids]
    return sub_nodes, sub_edges


def _resolve_graph(graph_file: Path, bundle_root: Path, notes: list[dict], threshold_bytes: int) -> dict:
    """Decide how to attach the graph; degrade cleanly on missing/stale/unreadable/broken."""
    info: dict = {
        "graph_present": graph_file.is_file(),
        "graph_stale": False,
        "graph_used": "absent",
        "graph_size_kb": None,
        "warning": None,
        "graph": None,
    }
    if not info["graph_present"]:
        info["warning"] = "knowledge graph missing — semantic search only"
        return info

    size = graph_file.stat().st_size
    info["graph_size_kb"] = round(size / 1024, 2)
    if graph_is_stale(graph_file, bundle_root):
        info["graph_stale"] = True
        info["warning"] = "knowledge graph is older than the wiki — semantic search only"
        return info

    try:
        nodes, edges = load_graph(graph_file)
    except (OSError, json.JSONDecodeError) as exc:
        info["warning"] = f"knowledge graph unreadable ({exc}) — semantic search only"
        return info

    if size <= threshold_bytes:
        info["graph_used"] = "whole"
        info["graph"] = {"nodes": nodes, "edges": edges}
    else:
        sub_nodes, sub_edges = select_subgraph(nodes, edges, notes)
        info["graph_used"] = "subgraph"
        info["graph"] = {"nodes": sub_nodes, "edges": sub_edges}
    return info


def _write_search_log(config: dict, config_path: Path, package: dict, strategy: str) -> bool:
    """Append one local entry (spec 06). Never raises — logging must not block the search."""
    log_cfg = config.get("search_log", {})
    if not log_cfg.get("enabled", True):
        return False
    raw_path = Path(log_cfg.get("path", DEFAULT_LOG_PATH))
    log_path = raw_path if raw_path.is_absolute() else config_path.resolve().parent / raw_path
    entry = {
        "timestamp": utc_now(),
        "query": package["query"],
        "strategy": strategy,
        "result_count": len(package["notes"]),
        "graph_used": package["graph_used"],
        "graph_present": package["graph_present"],
        "elapsed_ms": package["elapsed_ms"],
    }
    return search_log.log_search(log_path, entry)


def assemble(
    *,
    config_path: Path,
    query: str,
    top_k: int | None = None,
    runner: object | None = None,
    graph_path: Path | None = None,
    bundle_root: Path | None = None,
    log: bool = True,
) -> dict:
    """Return the CAG context package. Degrades cleanly; never raises for expected conditions."""
    started = time.perf_counter()
    config = load_config(config_path)
    repo = config_path.resolve().parent
    cag_cfg = {**{"graph_threshold_kb": DEFAULT_GRAPH_THRESHOLD_KB}, **config.get("cag", {})}
    threshold_bytes = int(cag_cfg["graph_threshold_kb"]) * 1024
    graph_file = graph_path or (repo / config["graph_json"])
    bundle = bundle_root or (repo / config["bundle_root"])

    search = query_index.search(config_path=config_path, query=query, top_k=top_k, runner=runner)
    notes = search.get("results", [])
    strategy = query_index.read_retrieval_config(config)[0]

    graph_info = _resolve_graph(graph_file, bundle, notes, threshold_bytes)
    package: dict = {
        "query": query,
        "esitoRicerca": search["esito"],
        "kb_consulted": True,
        "note_citate": [{"docTitle": n.get("docTitle"), "sourcePath": n.get("sourcePath")} for n in notes],
        "graph_threshold_kb": cag_cfg["graph_threshold_kb"],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "notes": notes,
        **graph_info,
    }

    if log:
        _write_search_log(config, config_path, package, strategy)
    return package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble the CAG context (notes + knowledge graph).")
    parser.add_argument("query", help="question or topic, in natural language")
    parser.add_argument("--top", type=int, default=None, help="number of results (default: config)")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"config path (default {DEFAULT_CONFIG})")
    args = parser.parse_args(argv)

    package = assemble(config_path=Path(args.config), query=args.query, top_k=args.top)
    print(json.dumps(package, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
