"""Deterministic kebab-case slugs for input roots."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _NON_ALNUM.sub("-", ascii_value.lower()).strip("-")
    return slug or "root"


def root_slug(root: Path, taken: Iterable[str] = ()) -> str:
    """Return a unique slug; collisions use deterministic ``-2``, ``-3`` suffixes."""

    base = slugify(Path(root).name)
    used = set(taken)
    if base not in used:
        return base
    index = 2
    while f"{base}-{index}" in used:
        index += 1
    return f"{base}-{index}"
