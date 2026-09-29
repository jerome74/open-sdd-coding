#!/usr/bin/env python3
"""Semantic search over the vector index — local, in-process embeddings.

Loads the index produced by ``build_index.py`` (single file or manifest + parts), embeds the
query with the **same** local model, and returns the top-K chunks by cosine similarity. If the
index was produced by a different embedding service/model than the one configured, the search
stops with ``erroreModello`` (BR-11) instead of comparing vectors from incompatible spaces.

Prints JSON:
    {"query": ..., "esito": ..., "results": [{"score", "docTitle", "sourcePath", "chunkIndex", "rawText", "expanded"}]}
    `expanded` is true for neighbours added by extended retrieval (QACE), false for a direct hit.

``esito`` ∈ {conRisultati, nessunRisultato, erroreModello, erroreRuntime}. An empty ``results``
with ``esito == nessunRisultato`` is the signal for the no-fabrication rule (BR-1), not an error.

Usage
    python3 query_index.py "<question or topic>" [--top K] [--config PATH]
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from pathlib import Path

# Reuse the embedding runner + backend resolution from the sibling builder (same skill scripts dir).
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import build_index  # noqa: E402

ESITO_HIT = "conRisultati"
ESITO_NONE = "nessunRisultato"
ESITO_MODEL = "erroreModello"
ESITO_RUNTIME = "erroreRuntime"

DEFAULT_TOP_K = 5
DEFAULT_MIN_SCORE = 0.80

DEFAULT_STRATEGY = "standard"
DEFAULT_NEIGHBOR_WIDTH = 1
DEFAULT_MAX_EXTENDED_BLOCKS = 15
WIDTH_MIN, WIDTH_MAX = 0, 3
MAX_BLOCKS_MIN, MAX_BLOCKS_MAX = 5, 30


def load_index(index_file: Path) -> dict:
    """Return {"embedding", "status", "items"} resolving either index layout (spec 01)."""
    index_root = index_file.parent
    if index_file.is_file():
        data = json.loads(index_file.read_text(encoding="utf-8"))
        return {
            "embedding": data.get("embedding", {}),
            "status": data.get("status"),
            "items": data.get("items", []),
        }
    manifest_file = index_root / "manifest.json"
    if manifest_file.is_file():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        items: list[dict] = []
        for part in manifest.get("parts", []):
            part_path = index_root / "parts" / part["name"]
            with gzip.open(part_path, "rt", encoding="utf-8") as handle:
                items.extend(json.load(handle).get("items", []))
        return {
            "embedding": manifest.get("embedding", {}),
            "status": manifest.get("status"),
            "items": items,
        }
    raise FileNotFoundError(f"no index at {index_file} or {manifest_file}")


def model_mismatch(index_embedding: dict, configured: dict) -> str | None:
    """Return a human-readable reason when the index cannot be trusted for this model (BR-11)."""
    index_model = index_embedding.get("model")
    conf_model = configured.get("model")
    if not index_model:
        return "index does not declare an embedding model; regenerate the index"
    if conf_model and index_model != conf_model:
        return f"index model {index_model!r} != configured model {conf_model!r}; regenerate the index"
    index_service = index_embedding.get("service")
    conf_service = configured.get("service")
    if index_service and conf_service and index_service != conf_service:
        return f"index service {index_service!r} != configured service {conf_service!r}; regenerate the index"
    return None


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def format_result(score: float, item: dict, expanded: bool = False) -> dict:
    return {
        "score": round(score, 4),
        "docTitle": item.get("docTitle"),
        "sourcePath": item.get("sourcePath"),
        "chunkIndex": item.get("chunkIndex"),
        "rawText": item.get("rawText"),
        "expanded": expanded,
    }


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def read_retrieval_config(config: dict) -> tuple[str, int, int]:
    """Return (strategy, neighbor_width, max_extended_blocks), clamped to BR-3 limits."""
    retrieval = config.get("retrieval", {})
    strategy = retrieval.get("strategy", DEFAULT_STRATEGY)
    if strategy not in ("standard", "esteso"):
        strategy = DEFAULT_STRATEGY
    width = _clamp(int(retrieval.get("neighbor_width", DEFAULT_NEIGHBOR_WIDTH)), WIDTH_MIN, WIDTH_MAX)
    max_blocks = _clamp(
        int(retrieval.get("max_extended_blocks", DEFAULT_MAX_EXTENDED_BLOCKS)),
        MAX_BLOCKS_MIN,
        MAX_BLOCKS_MAX,
    )
    return strategy, width, max_blocks


def expand_results(results: list[dict], items: list[dict], width: int, max_blocks: int) -> list[dict]:
    """QACE: add the `chunkIndex ± width` neighbours (same note) to each hit.

    Neighbours keep the origin's score and are flagged `expanded`; duplicates (from overlapping
    windows) are dropped; the total is capped at `max_blocks`.
    """
    by_path: dict[str, dict[int, dict]] = {}
    for item in items:
        by_path.setdefault(item.get("sourcePath"), {})[item.get("chunkIndex")] = item

    out: list[dict] = []
    seen: set[tuple] = set()
    for result in results:
        path = result["sourcePath"]
        index = result["chunkIndex"]
        if (path, index) not in seen:
            seen.add((path, index))
            out.append({**result, "expanded": False})
        chunks = by_path.get(path, {})
        for offset in range(-width, width + 1):
            if offset == 0:
                continue
            neighbour = chunks.get(index + offset)
            key = (neighbour.get("sourcePath"), neighbour.get("chunkIndex")) if neighbour else None
            if neighbour is None or key in seen:
                continue
            seen.add(key)
            out.append(format_result(result["score"], neighbour, expanded=True))
        if len(out) >= max_blocks:
            break
    return out[:max_blocks]


def search(
    *,
    config_path: Path,
    query: str,
    top_k: int | None = None,
    index_path: Path | None = None,
    runner: object | None = None,
) -> dict:
    """Run the semantic search. Never raises for expected conditions — returns an `esito`."""
    config = build_index.load_config(config_path)
    repo = config_path.resolve().parent
    emb_cfg = {**build_index.DEFAULT_EMBEDDING, **config.get("embedding", {})}
    search_cfg = config.get("search", {})
    top_k = top_k or int(search_cfg.get("top_k", DEFAULT_TOP_K))
    min_score = float(search_cfg.get("min_score", DEFAULT_MIN_SCORE))
    metric = str(search_cfg.get("metric", "cosine"))
    index_file = index_path or (repo / config["semantic_index"])

    try:
        index = load_index(index_file)
    except (FileNotFoundError, OSError) as exc:
        return {"esito": ESITO_RUNTIME, "query": query, "results": [], "error": str(exc)}

    if metric != "cosine":
        return {
            "esito": ESITO_RUNTIME,
            "query": query,
            "results": [],
            "error": f"unsupported search metric {metric!r} (only 'cosine' is implemented)",
        }
    if not index["items"]:
        return {"esito": ESITO_NONE, "query": query, "results": []}

    mismatch = model_mismatch(index["embedding"], emb_cfg)
    if mismatch:
        return {"esito": ESITO_MODEL, "query": query, "results": [], "error": mismatch}

    if runner is None:
        runner = build_index.EmbeddingRunner(emb_cfg["service"], emb_cfg["model"], emb_cfg.get("dimension"))
    try:
        query_vector = runner.embed([query], kind="query")[0]  # type: ignore[attr-defined]
    except build_index.IndexBuildError as exc:
        return {"esito": ESITO_RUNTIME, "query": query, "results": [], "error": str(exc)}

    scored = []
    for item in index["items"]:
        vector = item.get("vector")
        if not vector:
            continue
        scored.append((cosine(query_vector, vector), item))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    results = [format_result(score, item) for score, item in scored[:top_k] if score >= min_score]
    if results:
        strategy, width, max_blocks = read_retrieval_config(config)
        if strategy == "esteso":
            results = expand_results(results, index["items"], width, max_blocks)
    esito = ESITO_HIT if results else ESITO_NONE
    return {"esito": esito, "query": query, "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Semantic search over the vector index.")
    parser.add_argument("query", help="question or topic, in natural language")
    parser.add_argument("--top", type=int, default=None, help="number of results (default: config)")
    parser.add_argument("--config", default=build_index.DEFAULT_CONFIG,
                        help=f"config path (default {build_index.DEFAULT_CONFIG})")
    args = parser.parse_args(argv)

    result = search(config_path=Path(args.config), query=args.query, top_k=args.top)
    payload = {"query": args.query, "esito": result["esito"], "results": result["results"]}
    if result.get("error"):
        payload["error"] = result["error"]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result["esito"] in (ESITO_HIT, ESITO_NONE) else 2


if __name__ == "__main__":
    raise SystemExit(main())
