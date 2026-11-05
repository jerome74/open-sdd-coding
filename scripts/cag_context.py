#!/usr/bin/env python3
"""CAG adapter for semantic-first typed graph retrieval (FR-010/FR-011).

Existing notes/citations/log fields are preserved. Graph attachment is bounded and
requires a valid LPG sidecar and content manifest; legacy Graphify JSON is never
attached wholesale. Use graph_build.py to create the sidecar after wiki/index build.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# The retrieval engine lives in the wiki-semantic-search skill's scripts dir; reuse it read-only.
SKILL_SCRIPTS = REPO_ROOT / ".opencode" / "skills" / "wiki-semantic-search" / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))
import query_index  # noqa: E402

import graph_retrieval

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
    """Compatibility adapter; detailed fallback diagnostics remain visible."""
    config = load_config(config_path)
    options = {k: v for k, v in config.get("graph_retrieval", {}).items()
               if k in {"max_hops", "relation_types", "direction", "max_nodes",
                        "max_edges", "max_tokens", "timeout_ms"}}
    result = graph_retrieval.retrieve(config_path=config_path, query=query, top_k=top_k,
                                     runner=runner, graph_path=graph_path,
                                     bundle_root=bundle_root, **options)
    state = result["graph_status"]
    graph_file = graph_path or (config_path.resolve().parent / config.get("lpg_json", config["graph_json"]))
    esito = result.get("esito", "erroreRuntime")
    package = {
        **result,
        "esitoRicerca": esito,
        "kb_consulted": True,
        "note_citate": [{"docTitle": n.get("docTitle"), "sourcePath": n.get("sourcePath")}
                        for n in result["notes"]],
        "graph_threshold_kb": config.get("cag", {}).get("graph_threshold_kb", DEFAULT_GRAPH_THRESHOLD_KB),
        "graph_present": graph_file.is_file(),
        "graph_stale": state == "stale_artifacts",
        "graph_used": "subgraph" if result["relations"] else "absent",
        "graph_size_kb": round(graph_file.stat().st_size / 1024, 2) if graph_file.is_file() else None,
        "warning": "; ".join(result["diagnostics"]) or None,
        "graph": {"paths": result["node_paths"], "edges": [x["edge"] for x in result["relations"]]}
                 if result["relations"] else None,
    }
    if log:
        _write_search_log(config, config_path, package, query_index.read_retrieval_config(config)[0])
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
