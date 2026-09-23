#!/usr/bin/env python3
"""Lexical search over index/index.json — no embeddings, no external model.

Scores each chunk by term-overlap with the query (docTitle matches weighted higher than
rawText matches). Prints JSON: {"query": ..., "results": [...]}, empty "results" means no match.
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = REPO_ROOT / "knowledge-config.json"
TITLE_WEIGHT = 3
SNIPPET_CHARS = 280


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def tokenize(text):
    return [t for t in re.findall(r"[a-zA-Z0-9àèéìòù]+", text.lower()) if len(t) > 2]


def snippet_around(text, terms):
    lower = text.lower()
    pos = next((lower.find(t) for t in terms if lower.find(t) != -1), -1)
    if pos == -1:
        return text[:SNIPPET_CHARS].strip()
    start = max(0, pos - SNIPPET_CHARS // 2)
    end = min(len(text), start + SNIPPET_CHARS)
    return ("…" if start > 0 else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def score_item(item, query_terms):
    title_terms = tokenize(item.get("docTitle", ""))
    body_terms = tokenize(item.get("rawText", ""))
    score = 0
    for term in query_terms:
        score += title_terms.count(term) * TITLE_WEIGHT
        score += body_terms.count(term)
    return score


def search(index_path, query, top_n):
    with open(index_path, encoding="utf-8") as f:
        data = json.load(f)

    query_terms = tokenize(query)
    if not query_terms:
        return []

    scored = []
    for item in data.get("items", []):
        score = score_item(item, query_terms)
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = []
    for score, item in scored[:top_n]:
        results.append(
            {
                "score": score,
                "docTitle": item.get("docTitle"),
                "sourcePath": item.get("sourcePath"),
                "chunkIndex": item.get("chunkIndex"),
                "totalChunks": item.get("totalChunks"),
                "snippet": snippet_around(item.get("rawText", ""), query_terms),
            }
        )
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    config = load_config()
    index_path = REPO_ROOT / config["semantic_index"]

    if not index_path.is_file():
        print(json.dumps({"query": args.query, "error": f"index not found: {index_path}", "results": []}))
        return 2

    results = search(index_path, args.query, args.top)
    print(json.dumps({"query": args.query, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
