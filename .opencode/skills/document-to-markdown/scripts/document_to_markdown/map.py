"""Conversion map: schema, atomic persistence, and incremental skip logic."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import ConversionError

MAP_FILENAME = ".conversion-map.json"
MAP_VERSION = 1
ENTRY_KEYS = (
    "status",
    "converted",
    "media",
    "tool",
    "source_sha256",
    "converted_sha256",
    "error",
)
SKIPPABLE_STATUSES = ("ok", "skipped")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_map(root_name: str) -> dict[str, Any]:
    return {
        "version": MAP_VERSION,
        "root": root_name,
        "generated_at": now_iso(),
        "entries": {},
    }


def make_entry(
    *,
    status: str,
    converted: str | None = None,
    media: str | None = None,
    tool: str | None = None,
    source_sha256: str | None = None,
    converted_sha256: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    if status == "error" and source_sha256 is not None:
        raise ValueError("source_sha256 deve essere null con status 'error'")
    return {
        "status": status,
        "converted": converted,
        "media": media,
        "tool": tool,
        "source_sha256": source_sha256,
        "converted_sha256": converted_sha256,
        "error": error,
    }


def load_map(path: str | Path, root_name: str) -> dict[str, Any]:
    map_path = Path(path)
    if not map_path.is_file():
        return new_map(root_name)
    try:
        data = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConversionError(f"mappa non valida '{map_path}': {exc}", code="MAP") from exc
    if not isinstance(data, dict):
        raise ConversionError(f"mappa non valida '{map_path}': atteso un oggetto JSON", code="MAP")
    if data.get("version") != MAP_VERSION:
        raise ConversionError(
            f"mappa non valida '{map_path}': version attesa {MAP_VERSION}, trovata {data.get('version')!r}",
            code="MAP",
        )
    if not isinstance(data.get("entries"), dict):
        raise ConversionError(f"mappa non valida '{map_path}': 'entries' non è un oggetto", code="MAP")
    if not isinstance(data.get("root"), str):
        raise ConversionError(f"mappa non valida '{map_path}': 'root' mancante", code="MAP")
    return data


def write_map_atomic(path: str | Path, data: dict[str, Any]) -> None:
    map_path = Path(path)
    map_path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{map_path.name}.", suffix=".tmp", dir=str(map_path.parent)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, map_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def upsert_entry(data: dict[str, Any], key: str, entry: dict[str, Any]) -> dict[str, Any]:
    data.setdefault("entries", {})[key] = entry
    data["generated_at"] = now_iso()
    return data


def should_skip(
    entry: dict[str, Any] | None,
    source_sha256: str,
    out_root: str | Path,
) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("status") not in SKIPPABLE_STATUSES:
        return False
    if entry.get("source_sha256") != source_sha256:
        return False
    converted = entry.get("converted")
    if not isinstance(converted, str) or not (Path(out_root) / converted).is_file():
        return False
    media = entry.get("media")
    if media is None:
        return True
    return isinstance(media, str) and (Path(out_root) / media).is_dir()
