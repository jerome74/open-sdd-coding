"""Skill-local configuration.

Defaults:

- ``out_dir = "graphify-out/derived"`` (relative to the current directory)
- ``pdf_dpi = 120``
- ``skip_unchanged = true``
- ``prune = false``

``prune: true`` is rejected with ``ConfigError`` (exit 2) until the prune
intervention lands. The module never reads or writes repository config files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .errors import ConfigError, PathError
from .guard import is_within, resolve_path

DEFAULT_OUT_DIR = "graphify-out/derived"
DEFAULT_PDF_DPI = 120

_ALLOWED_KEYS = {"out_dir", "pdf_dpi", "skip_unchanged", "prune"}


@dataclass(frozen=True)
class Config:
    out_dir: Path = Path(DEFAULT_OUT_DIR)
    pdf_dpi: int = DEFAULT_PDF_DPI
    skip_unchanged: bool = True
    prune: bool = False


def _as_bool(value: Any, key: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"chiave '{key}': atteso booleano, trovato {type(value).__name__}")
    return value


def _as_int(value: Any, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"chiave '{key}': atteso intero, trovato {type(value).__name__}")
    return value


def _as_out_dir(value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("chiave 'out_dir': attesa stringa non vuota")
    return Path(value).expanduser()


def load_config(path: Path | None = None, *, out_dir: str | Path | None = None) -> Config:
    """Load config from an optional JSON file, then apply the ``--out`` override."""

    values: dict[str, Any] = {}
    if path is not None:
        config_path = Path(path).expanduser()
        try:
            raw = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"impossibile leggere la configurazione '{config_path}': {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"configurazione non valida '{config_path}': {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"configurazione '{config_path}': atteso un oggetto JSON")
        unknown = sorted(set(data) - _ALLOWED_KEYS)
        if unknown:
            raise ConfigError(f"configurazione '{config_path}': chiavi non supportate: {', '.join(unknown)}")
        values = data

    cfg = Config()
    if "out_dir" in values:
        cfg = replace(cfg, out_dir=_as_out_dir(values["out_dir"]))
    if "pdf_dpi" in values:
        dpi = _as_int(values["pdf_dpi"], "pdf_dpi")
        if dpi <= 0:
            raise ConfigError("chiave 'pdf_dpi': deve essere maggiore di zero")
        cfg = replace(cfg, pdf_dpi=dpi)
    if "skip_unchanged" in values:
        cfg = replace(cfg, skip_unchanged=_as_bool(values["skip_unchanged"], "skip_unchanged"))
    if "prune" in values:
        prune = _as_bool(values["prune"], "prune")
        if prune:
            raise ConfigError("prune non implementato: impostare 'prune' a false")
        cfg = replace(cfg, prune=prune)

    if out_dir is not None:
        cfg = replace(cfg, out_dir=_as_out_dir(str(out_dir)))

    return replace(cfg, out_dir=resolve_path(cfg.out_dir))


def validate_out_dir(config: Config, roots: list[Path]) -> None:
    """Reject an output directory that equals or lives inside an input root."""

    out_dir = resolve_path(config.out_dir)
    for root in roots:
        resolved = resolve_path(root)
        if out_dir == resolved:
            raise PathError(f"la directory di output '{out_dir}' coincide con il root di input '{resolved}'")
        if is_within(out_dir, resolved):
            raise PathError(f"la directory di output '{out_dir}' è dentro il root di input '{resolved}'")
