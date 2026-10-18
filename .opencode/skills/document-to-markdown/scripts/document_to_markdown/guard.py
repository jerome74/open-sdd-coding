"""Path safety helpers.

Every path crossing the engine boundary is resolved first, so ``..`` and
symlinks cannot escape the configured output directory or an input root.
"""

from __future__ import annotations

from pathlib import Path

from .errors import PathError


def resolve_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def is_within(path: str | Path, parent: str | Path) -> bool:
    resolved = resolve_path(path)
    base = resolve_path(parent)
    try:
        resolved.relative_to(base)
    except ValueError:
        return False
    return True


def ensure_within(path: str | Path, parent: str | Path, *, label: str = "path") -> Path:
    resolved = resolve_path(path)
    if not is_within(resolved, parent):
        raise PathError(f"{label} '{resolved}' esce da '{resolve_path(parent)}'")
    return resolved


def assert_writable(path: str | Path, roots: list[Path], out_dir: str | Path) -> Path:
    """Return ``path`` resolved if it is writable, else raise ``PathError``."""

    resolved = resolve_path(path)
    destination = resolve_path(out_dir)
    if not is_within(resolved, destination):
        raise PathError(f"scrittura rifiutata: '{resolved}' non è dentro '{destination}'")
    for root in roots:
        if is_within(resolved, root):
            raise PathError(f"scrittura rifiutata: '{resolved}' è dentro il root di input '{resolve_path(root)}'")
    return resolved
