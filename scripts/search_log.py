#!/usr/bin/env python3
"""Local search log — append one JSON line per search. Local only, never blocking.

FR-009 / BR-7: every search records, **locally**, the question, the strategy used, the number of
results, whether the graph was present/used, and the elapsed time. Nothing is sent to an external
service, and a write failure must **not** propagate — the search has already succeeded and must not
be degraded by logging.

The log is JSON Lines (append-only), one object per line.
"""

from __future__ import annotations

import json
from pathlib import Path

FIELDS = (
    "timestamp",
    "query",
    "strategy",
    "result_count",
    "graph_used",
    "graph_present",
    "elapsed_ms",
)


def log_search(log_path: Path, entry: dict) -> bool:
    """Append `entry` as one JSON line to `log_path`. Returns True on success, False otherwise.

    Never raises: any failure (missing directory that cannot be created, permission denied, a
    non-serialisable value) is swallowed so the search flow is never blocked (FR-009 alt).
    """
    try:
        if not isinstance(entry, dict):
            return False
        log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({key: entry.get(key) for key in FIELDS}, ensure_ascii=False)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return True
    except (OSError, TypeError, ValueError):
        return False


if __name__ == "__main__":  # pragma: no cover — module is imported, not run
    raise SystemExit("search_log is a library module; import log_search().")
