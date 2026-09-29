#!/usr/bin/env python3
"""Build the semantic (vector) index over the wiki bundle — local, in-process.

Reads ``bundle_root``, ``semantic_index`` and the ``embedding`` / ``index`` blocks from
``knowledge-config.json`` (never hard-codes a path). Every chunk gets an embedding vector
from a single local model; the payload declares the embedding service/model/dimension so a
query computed with a different model can be refused (BR-11).

Schema v2 (supersedes the lexical v1 that carried ``rawText`` only):

    index/index.json                             # single file, size <= threshold
    index/manifest.json + index/parts/*.json.gz  # compressed, size > threshold (BR-4)
    index/_state.json                            # status sidecar (BR-8)

Writes are atomic: a staged directory is swapped in only once complete, so a partial or
failed build never replaces a valid index. Chunk parameters, the size threshold and the
embedding model are configuration, not constants.

Usage
    python3 build_index.py [--config PATH]
    python3 build_index.py --status
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

DEFAULT_CONFIG = "knowledge-config.json"
INDEX_SCHEMA_VERSION = 2
DEFAULT_CHUNK_WORDS = 250
DEFAULT_OVERLAP = 0
DEFAULT_THRESHOLD_MB = 50
DEFAULT_EMBEDDING = {
    "service": "local",
    "model": "intfloat/multilingual-e5-small",
    "dimension": None,
}

STATUS_OK = "generato"
STATUS_WITH_ERRORS = "generato con errori"
STATUS_FAILED = "fallito"
STATUS_MISSING = "assente"

# A backend maps a list of texts to a list of vectors (one per text), fully in-process.
EmbedBackend = Callable[[list[str]], list[list[float]]]


class IndexBuildError(Exception):
    """Fatal build condition (e.g. embedding model unavailable, unreadable bundle)."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- config


def load_config(config_path: Path) -> dict:
    if not config_path.is_file():
        raise IndexBuildError(f"config not found: {config_path}")
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IndexBuildError(f"config is not valid JSON: {config_path}: {exc}") from exc


# --------------------------------------------------------------------------- chunking


def strip_frontmatter(text: str) -> tuple[str, str | None]:
    """Return (body, title). Frontmatter is removed; the title is preserved when present."""
    if not text.startswith("---"):
        return text, None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text, None
    frontmatter, body = parts[1], parts[2]
    match = re.search(r'^title:\s*"?(.+?)"?\s*$', frontmatter, re.MULTILINE)
    return body, (match.group(1) if match else None)


def chunk_words(text: str, size: int, overlap: int = 0) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    step = max(1, size - overlap)
    chunks: list[str] = []
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start : start + size]))
        if start + size >= len(words):
            break
    return chunks


def chunk_note(md_path: Path, bundle_root: Path, size: int, overlap: int) -> list[dict]:
    rel_path = md_path.relative_to(bundle_root).as_posix()
    raw = md_path.read_text(encoding="utf-8")
    body, title = strip_frontmatter(raw)
    doc_title = title or md_path.stem
    pieces = chunk_words(body.strip(), size, overlap)
    total = len(pieces)
    return [
        {
            "id": hashlib.sha1(f"{rel_path}#{idx}".encode()).hexdigest(),
            "docTitle": doc_title,
            "sourcePath": rel_path,
            "chunkIndex": idx,
            "totalChunks": total,
            "rawText": piece,
        }
        for idx, piece in enumerate(pieces)
    ]


def chunk_bundle(bundle_root: Path, size: int, overlap: int) -> tuple[list[dict], list[dict]]:
    """Chunk every note. A single unreadable note is reported, never fatal (FR-001 alt)."""
    items: list[dict] = []
    errors: list[dict] = []
    for md_path in sorted(bundle_root.rglob("*.md")):
        try:
            items.extend(chunk_note(md_path, bundle_root, size, overlap))
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(
                {"sourcePath": md_path.relative_to(bundle_root).as_posix(), "error": str(exc)}
            )
    return items, errors


# --------------------------------------------------------------------------- embedding


def _needs_e5_prefix(model_name: str) -> bool:
    return "e5" in model_name.lower()


def _load_backend(model_name: str) -> EmbedBackend:
    """Resolve a local, in-process embedding backend. Never performs a network call.

    Backends are tried in order (fastembed/ONNX first, then sentence-transformers). A backend
    that is installed but does not support the requested model does **not** abort resolution —
    the next candidate is tried, so the model decided in the spec is served by whichever backend
    can actually load it.
    """
    errors: list[str] = []

    try:
        from fastembed import TextEmbedding  # type: ignore
    except ImportError:
        TextEmbedding = None  # type: ignore
    if TextEmbedding is not None:
        try:
            fast_model = TextEmbedding(model_name=model_name)
        except Exception as exc:  # noqa: BLE001 — try the next backend
            errors.append(f"fastembed: {exc}")
        else:

            def embed(texts: list[str], _model=fast_model) -> list[list[float]]:
                return [[float(x) for x in vec] for vec in _model.embed(texts)]

            return embed

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ImportError:
        SentenceTransformer = None  # type: ignore
    if SentenceTransformer is not None:
        try:
            st_model = SentenceTransformer(model_name)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"sentence-transformers: {exc}")
        else:

            def embed(texts: list[str], _model=st_model) -> list[list[float]]:
                return [[float(x) for x in vec] for vec in _model.encode(texts)]

            return embed

    detail = "; ".join(errors) if errors else (
        "no local embedding backend installed — install 'fastembed' or 'sentence-transformers'"
    )
    raise IndexBuildError(
        f"no local embedding backend could serve {model_name!r}: {detail}; "
        "indexing must stay on-machine (constitution, Principio 6)"
    )


class EmbeddingRunner:
    """Loads the local embedding model once and vectorises passages/queries."""

    def __init__(
        self,
        service: str,
        model: str,
        dimension: int | None = None,
        backend: EmbedBackend | None = None,
    ) -> None:
        self.service = service
        self.model = model
        self.dimension = dimension
        self._backend = backend

    @property
    def embedding_id(self) -> dict:
        return {"service": self.service, "model": self.model, "dimension": self.dimension}

    def embed(self, texts: list[str], kind: str = "passage") -> list[list[float]]:
        if self._backend is None:
            self._backend = _load_backend(self.model)
        if kind in ("passage", "query") and _needs_e5_prefix(self.model):
            payload = [f"{kind}: {text}" for text in texts]
        else:
            payload = list(texts)
        vectors = self._backend(payload)
        if self.dimension is None and vectors:
            self.dimension = len(vectors[0])
        return vectors


# --------------------------------------------------------------------------- payload


def build_payload(
    items: list[dict],
    errors: list[dict],
    source_bundle: str,
    embedding: dict,
    status: str,
) -> dict:
    return {
        "version": INDEX_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "source_bundle": source_bundle,
        "status": status,
        "embedding": embedding,
        "errors": errors,
        "items": items,
    }


# --------------------------------------------------------------------------- serialization


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_gz_json(path: Path, data: object) -> int:
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    with gzip.open(path, "wb") as handle:
        handle.write(raw)
    return path.stat().st_size


def _partition(items: list[dict], max_bytes: int) -> list[list[dict]]:
    """Split items so each group's serialized size stays within `max_bytes`."""
    groups: list[list[dict]] = []
    current: list[dict] = []
    current_bytes = 0
    for item in items:
        item_bytes = len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
        if current and current_bytes + item_bytes > max_bytes:
            groups.append(current)
            current, current_bytes = [], 0
        current.append(item)
        current_bytes += item_bytes
    if current or not groups:
        groups.append(current)
    return groups


def serialize_index(
    stage_root: Path, payload: dict, threshold_bytes: int, index_filename: str = "index.json"
) -> dict:
    """Write the index into the already-created `stage_root`. Returns a summary.

    `index_filename` is the single-file name, derived from the configured `semantic_index`
    (Principio 5); it is never assumed to be `index.json`. The compressed layout's manifest is
    named `manifest.json` (layout constant documented in the plan, OTQ-03).
    """
    items = payload["items"]
    full = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(full) <= threshold_bytes:
        _write_json(stage_root / index_filename, payload)
        return {"format": "single", "parts": [], "totalItems": len(items)}

    parts_dir = stage_root / "parts"
    parts_dir.mkdir()
    manifest = {key: value for key, value in payload.items() if key != "items"}
    manifest["totalItems"] = len(items)
    manifest["parts"] = []
    for index, group in enumerate(_partition(items, threshold_bytes)):
        name = f"part-{index:03d}.json.gz"
        size = _write_gz_json(parts_dir / name, {"items": group})
        manifest["parts"].append({"name": name, "itemCount": len(group), "size": size})
    _write_json(stage_root / "manifest.json", manifest)
    return {"format": "compressed", "parts": manifest["parts"], "totalItems": len(items)}


def swap_into_place(stage_root: Path, index_root: Path) -> None:
    """Atomically replace `index_root` with `stage_root`, keeping a recoverable backup."""
    index_root.parent.mkdir(parents=True, exist_ok=True)
    backup = index_root.parent / (index_root.name + ".bak")
    if backup.exists():
        shutil.rmtree(backup)
    if index_root.exists():
        os.replace(index_root, backup)
    try:
        os.replace(stage_root, index_root)
    except OSError:
        if backup.exists() and not index_root.exists():
            os.replace(backup, index_root)  # rollback to the previous valid index
        raise
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)


# --------------------------------------------------------------------------- state


def write_state(index_root: Path, status: str, embedding: dict, error: str | None = None) -> None:
    index_root.mkdir(parents=True, exist_ok=True)
    state: dict = {"status": status, "generated_at": utc_now(), "embedding": embedding}
    if error:
        state["error"] = error
    _write_json(index_root / "_state.json", state)


# --------------------------------------------------------------------------- orchestration


def build_index(
    *,
    config_path: Path,
    runner: EmbeddingRunner | None = None,
    bundle_root: Path | None = None,
    index_path: Path | None = None,
    threshold_bytes: int | None = None,
) -> dict:
    """Build the index described by `config_path` and return a result summary.

    Raises `IndexBuildError` on a fatal condition; the previous index, if any, is left intact.
    """
    config = load_config(config_path)
    repo = config_path.resolve().parent
    emb_cfg = {**DEFAULT_EMBEDDING, **config.get("embedding", {})}
    idx_cfg = config.get("index", {})

    bundle = bundle_root or (repo / config["bundle_root"])
    index_file = index_path or (repo / config["semantic_index"])
    index_root = index_file.parent
    chunk_size = int(idx_cfg.get("chunk_words", DEFAULT_CHUNK_WORDS))
    overlap = int(idx_cfg.get("chunk_overlap", DEFAULT_OVERLAP))
    if threshold_bytes is None:
        threshold_bytes = int(idx_cfg.get("part_threshold_mb", DEFAULT_THRESHOLD_MB)) * 1024 * 1024

    stage: Path | None = None
    active: EmbeddingRunner | None = runner
    try:
        if not bundle.is_dir():
            raise IndexBuildError(f"bundle_root not found: {bundle}")
        if active is None:
            active = EmbeddingRunner(emb_cfg["service"], emb_cfg["model"], emb_cfg.get("dimension"))

        items, errors = chunk_bundle(bundle, chunk_size, overlap)
        if items:
            vectors = active.embed([item["rawText"] for item in items], kind="passage")
            if len(vectors) != len(items):
                raise IndexBuildError(
                    f"embedding backend returned {len(vectors)} vectors for {len(items)} chunks"
                )
            for item, vector in zip(items, vectors):
                item["vector"] = vector

        status = STATUS_WITH_ERRORS if errors else STATUS_OK
        payload = build_payload(items, errors, config["bundle_root"], active.embedding_id, status)

        stage = index_root.parent / (index_root.name + ".tmp")
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True)
        summary = serialize_index(stage, payload, threshold_bytes, index_file.name)
        swap_into_place(stage, index_root)
        write_state(index_root, status, active.embedding_id)
    except IndexBuildError as exc:
        _fail(stage, index_root, active, emb_cfg, str(exc))
        raise
    except Exception as exc:  # noqa: BLE001 — never leave a partial index behind
        wrapped = IndexBuildError(f"index build failed: {exc}")
        _fail(stage, index_root, active, emb_cfg, str(wrapped))
        raise wrapped from exc

    documents = len({item["sourcePath"] for item in items})
    return {
        "status": status,
        "items": len(items),
        "documents": documents,
        "errors": errors,
        "format": summary["format"],
        "parts": summary["parts"],
        "index_path": str(index_file),
        "embedding": active.embedding_id,
    }


def _fail(
    stage: Path | None,
    index_root: Path,
    active: EmbeddingRunner | None,
    emb_cfg: dict,
    message: str,
) -> None:
    if stage is not None and stage.exists():
        shutil.rmtree(stage, ignore_errors=True)
    embedding = active.embedding_id if active is not None else emb_cfg
    try:
        write_state(index_root, STATUS_FAILED, embedding, message)
    except OSError:
        pass


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the semantic (vector) index over the wiki bundle.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"config path (default {DEFAULT_CONFIG})")
    parser.add_argument("--status", action="store_true", help="print the last index status and exit")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    try:
        config = load_config(config_path)
    except IndexBuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    index_root = (config_path.resolve().parent / config["semantic_index"]).parent

    if args.status:
        state_file = index_root / "_state.json"
        if not state_file.is_file():
            print(json.dumps({"status": STATUS_MISSING}))
            return 1
        print(state_file.read_text(encoding="utf-8").strip())
        return 0

    try:
        result = build_index(config_path=config_path)
    except IndexBuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    extra = f" ({len(result['errors'])} note segnalate)" if result["errors"] else ""
    print(
        f"Built {result['index_path']} [{result['format']}]: "
        f"{result['items']} chunks from {result['documents']} documents — {result['status']}{extra}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
