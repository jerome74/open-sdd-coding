"""Discover convertible documents under an input root.

Discovery is read-only: it never creates, renames, or removes entries.
Unsupported extensions, hidden entries, Office lock files (``~$``), and
symlinks that resolve outside the root are ignored.
"""

from __future__ import annotations

import os
from pathlib import Path

from .errors import PathError
from .guard import is_within, resolve_path

MVP_EXTENSIONS = frozenset({".docx", ".docm", ".pptx", ".pptm", ".xlsx", ".xlsm", ".pdf"})
OPTIONAL_EXTENSIONS = frozenset({".doc", ".ppt", ".xls", ".odt", ".html", ".htm", ".csv", ".tsv"})
SUPPORTED_EXTENSIONS = MVP_EXTENSIONS | OPTIONAL_EXTENSIONS

_IGNORED_NAMES = frozenset({".DS_Store", "Thumbs.db"})
_IGNORED_SUFFIXES = frozenset({".tmp", ".lock", ".part"})


def _is_candidate(path: Path) -> bool:
    name = path.name
    if name.startswith(".") or name.startswith("~$"):
        return False
    if name in _IGNORED_NAMES:
        return False
    if path.suffix.lower() in _IGNORED_SUFFIXES:
        return False
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def discover(root: str | Path) -> list[Path]:
    """Return supported files, sorted by relative POSIX path."""

    root_path = resolve_path(root)
    if not root_path.is_dir():
        raise PathError(f"root di input non trovato o non è una directory: '{root_path}'")

    found: list[Path] = []
    for current, dirnames, filenames in os.walk(root_path, followlinks=False):
        current_path = Path(current)
        dirnames[:] = sorted(
            name for name in dirnames if not name.startswith(".") and not (current_path / name).is_symlink()
        )
        for name in filenames:
            candidate = current_path / name
            if not _is_candidate(candidate):
                continue
            if candidate.is_symlink() and not is_within(candidate, root_path):
                continue
            found.append(candidate)

    return sorted(found, key=lambda item: item.relative_to(root_path).as_posix())
