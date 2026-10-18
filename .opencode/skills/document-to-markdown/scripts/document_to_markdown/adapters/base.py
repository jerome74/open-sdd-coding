"""Adapter contract and external tool helpers."""

from __future__ import annotations

import abc
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..config import Config
from ..errors import ConversionError

TOOL_TIMEOUT_SECONDS = 180


@dataclass
class ConversionResult:
    converted: Path
    media: Path | None
    tool: str


class Adapter(abc.ABC):
    name: str
    suffixes: tuple[str, ...]

    @abc.abstractmethod
    def convert(
        self,
        source: Path,
        out_md: Path,
        media_dir: Path,
        config: Config,
    ) -> ConversionResult:
        """Write Markdown to ``out_md`` and media under ``media_dir``."""

    def matches(self, path: str | Path) -> bool:
        suffix = Path(path).suffix.lower()
        return suffix in {item.lower() for item in self.suffixes}


def require_tool(candidates: Sequence[str], *, label: str | None = None) -> str:
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    names = " o ".join(candidates)
    raise ConversionError(
        f"tool richiesto non trovato: {label or names}. Installarlo e riprovare.",
        code="TOOL_MISSING",
    )


def run_tool(command: Sequence[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            [str(item) for item in command],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ConversionError(f"tool non trovato: '{command[0]}'", code="TOOL_MISSING") from exc
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(
            f"timeout di {TOOL_TIMEOUT_SECONDS}s eseguendo '{command[0]}'",
            code="TOOL_TIMEOUT",
        ) from exc
    except OSError as exc:
        raise ConversionError(f"impossibile eseguire '{command[0]}': {exc}", code="TOOL_ERROR") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if not detail:
            detail = f"exit {result.returncode}"
        raise ConversionError(f"'{Path(command[0]).name}' è fallito: {detail}", code="TOOL_ERROR")
    return result
