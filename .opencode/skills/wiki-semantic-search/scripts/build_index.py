#!/usr/bin/env python3
"""Chunk graphify-out/wiki/*.md into index/index.json, natively inside Claude Code.

Reads bundle_root and semantic_index from knowledge-config.json. No embeddings: each
chunk carries plain text (rawText) for the lexical search in query_index.py.
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = REPO_ROOT / "knowledge-config.json"
CHUNK_WORDS = 250


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def strip_frontmatter(text):
    if not text.startswith("---"):
        return text, None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text, None
    frontmatter, body = parts[1], parts[2]
    title_match = re.search(r'^title:\s*"?(.+?)"?\s*$', frontmatter, re.MULTILINE)
    title = title_match.group(1) if title_match else None
    return body, title


def chunk_words(text, size):
    words = text.split()
    if not words:
        return [""]
    return [" ".join(words[i : i + size]) for i in range(0, len(words), size)]


def build_items(bundle_root):
    items = []
    for md_path in sorted(bundle_root.rglob("*.md")):
        rel_path = md_path.relative_to(bundle_root).as_posix()
        raw = md_path.read_text(encoding="utf-8")
        body, title = strip_frontmatter(raw)
        doc_title = title or md_path.stem
        chunks = chunk_words(body.strip(), CHUNK_WORDS)
        total = len(chunks)
        for idx, chunk_text in enumerate(chunks):
            item_id = hashlib.sha1(f"{rel_path}#{idx}".encode()).hexdigest()
            items.append(
                {
                    "id": item_id,
                    "docTitle": doc_title,
                    "sourcePath": rel_path,
                    "chunkIndex": idx,
                    "totalChunks": total,
                    "rawText": chunk_text,
                }
            )
    return items


def main():
    config = load_config()
    bundle_root = REPO_ROOT / config["bundle_root"]
    index_path = REPO_ROOT / config["semantic_index"]

    if not bundle_root.is_dir():
        print(f"ERROR: bundle_root not found: {bundle_root}", file=sys.stderr)
        return 2

    items = build_items(bundle_root)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_bundle": config["bundle_root"],
        "items": items,
    }
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    docs = len({it["sourcePath"] for it in items})
    print(f"Built {index_path}: {len(items)} chunks from {docs} documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
