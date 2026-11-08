"""C-07 Device Adapter — unico accesso a Termux:API, file e comandi.

Nessuna azione modificante senza ``approved=True`` (BR-2). La lettura dei log
passa solo da percorsi in allowlist (BR-13).

Spec 07: oltre a ``read_file`` l'adapter offre le primitive che C-29 usa per i
log — metadati di un percorso (``inspect_path``), coda limitata di un file
(``read_file_tail``) ed elenco non ricorsivo di una cartella (``list_files``).
Il filesystem resta accessibile solo da qui (Tech Stack).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from .errors import DeviceError, GateError

logger = logging.getLogger("agente.device")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]

# P-A-02 (spec 07): limiti di lettura dei log, non dichiarati dalle spec.
MAX_LOG_SLICE_CHARS = 8_000
MAX_LOG_FILES = 20
# Un carattere UTF-8 occupa al massimo 4 byte: il budget in byte copre sempre
# `max_chars` caratteri anche nel caso peggiore.
_TAIL_BYTES_PER_CHAR = 4


@dataclass(frozen=True)
class PathInfo:
    """Metadati di un percorso, senza aprirne il contenuto."""

    path: str
    exists: bool
    is_file: bool
    is_dir: bool
    size: int
    readable: bool


@dataclass(frozen=True)
class FileTail:
    """Coda di un file: ultimi ``max_chars`` caratteri e dimensione reale."""

    text: str
    size: int
    truncated: bool


@dataclass(frozen=True)
class DirectoryListing:
    """File regolari di una cartella, con ciò che è stato saltato."""

    files: tuple[str, ...]
    skipped_dirs: int
    skipped_links: int
    truncated: bool


class DeviceAdapter:
    def __init__(self, *, runner: Runner | None = None) -> None:
        self._run = runner or subprocess.run

    def battery_level(self) -> int:
        payload = self._termux_json("termux-battery-status")
        try:
            level = int(payload["percentage"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DeviceError("risposta termux-battery-status malformata") from exc
        return level

    def is_online(self) -> bool:
        payload = self._termux_json("termux-wifi-connectioninfo")
        # Termux:API espone lo stato del supplicant e l'IP assegnato.
        state = str(payload.get("supplicant_state", "")).upper()
        ip = str(payload.get("ip", "")).strip()
        return state == "COMPLETED" or (bool(ip) and ip != "0.0.0.0")

    def record_last_contact(self, settings: Any, when: datetime | None = None) -> str:
        """Salva in ``settings`` l'ultimo contatto di rete (meccanismo BR-10)."""
        moment = (when or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        settings.set("last_contact_at", moment)
        return moment

    def run_command(self, cmd: Sequence[str], approved: bool) -> "subprocess.CompletedProcess[str]":
        self._require_approval(approved, f"comando {' '.join(cmd)}")
        return self._execute(list(cmd))

    def read_file(
        self, path: str | Path, allowlist: Sequence[str], approved: bool = False
    ) -> str:
        """Legge un file solo se il percorso è dentro l'allowlist del compito."""
        candidate = Path(path).expanduser().resolve()
        if not _in_allowlist(candidate, allowlist):
            raise GateError(f"lettura fuori allowlist: {candidate}")
        logger.info(
            "lettura file",
            extra={"path": str(candidate), "approved": approved, "read_only": True},
        )
        try:
            return candidate.read_text(encoding="utf-8")
        except OSError as exc:
            raise DeviceError(f"lettura fallita: {exc}") from exc

    def inspect_path(
        self, path: str | Path, allowlist: Sequence[str]
    ) -> PathInfo:
        """Metadati del percorso (esistenza, tipo, dimensione, leggibilità)."""
        candidate = self._authorized_path(path, allowlist)
        try:
            exists = candidate.exists()
            is_file = candidate.is_file() if exists else False
            is_dir = candidate.is_dir() if exists else False
            size = candidate.stat().st_size if is_file else 0
            readable = (
                os.access(candidate, os.R_OK | os.X_OK)
                if is_dir
                else os.access(candidate, os.R_OK) if is_file else False
            )
        except OSError as exc:
            raise DeviceError(f"ispezione fallita: {exc}") from exc
        return PathInfo(
            path=str(candidate),
            exists=exists,
            is_file=is_file,
            is_dir=is_dir,
            size=size,
            readable=readable,
        )

    def read_file_tail(
        self,
        path: str | Path,
        allowlist: Sequence[str],
        *,
        max_chars: int = MAX_LOG_SLICE_CHARS,
    ) -> FileTail:
        """Legge la coda del file: ultimi ``max_chars`` caratteri (BR-13)."""
        candidate = self._authorized_path(path, allowlist)
        budget = max(1, max_chars)
        byte_budget = budget * _TAIL_BYTES_PER_CHAR
        try:
            size = candidate.stat().st_size
            with candidate.open("rb") as handle:
                handle.seek(max(0, size - byte_budget))
                raw = handle.read(byte_budget)
        except OSError as exc:
            raise DeviceError(f"lettura fallita: {exc}") from exc

        decoded = raw.decode("utf-8", errors="replace")
        truncated = size > len(raw) or len(decoded) > budget
        text = decoded[-budget:] if len(decoded) > budget else decoded
        logger.info(
            "lettura coda log",
            extra={
                "path": str(candidate),
                "size": size,
                "chars": len(text),
                "truncated": truncated,
            },
        )
        return FileTail(text=text, size=size, truncated=truncated)

    def list_files(
        self,
        directory: str | Path,
        allowlist: Sequence[str],
        *,
        limit: int = MAX_LOG_FILES,
    ) -> DirectoryListing:
        """Elenca i file regolari della cartella, senza ricorsione (BR-13)."""
        root = self._authorized_path(directory, allowlist)
        if not root.is_dir():
            raise DeviceError(f"non è una cartella: {root}")
        files: list[str] = []
        skipped_dirs = 0
        skipped_links = 0
        try:
            with os.scandir(root) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        skipped_links += 1
                    elif entry.is_dir(follow_symlinks=False):
                        skipped_dirs += 1
                    elif entry.is_file(follow_symlinks=False):
                        files.append(entry.path)
        except OSError as exc:
            raise DeviceError(f"elenco fallito: {exc}") from exc

        files.sort(key=lambda item: Path(item).name)
        truncated = len(files) > max(0, limit)
        logger.info(
            "elenco cartella log",
            extra={
                "path": str(root),
                "files": len(files),
                "skipped_dirs": skipped_dirs,
                "skipped_links": skipped_links,
                "truncated": truncated,
            },
        )
        return DirectoryListing(
            files=tuple(files[: max(0, limit)]),
            skipped_dirs=skipped_dirs,
            skipped_links=skipped_links,
            truncated=truncated,
        )

    def write_file(self, path: str | Path, content: str, approved: bool) -> None:
        self._require_approval(approved, f"scrittura {path}")
        target = Path(path).expanduser()
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise DeviceError(f"scrittura fallita: {exc}") from exc

    def delete_file(self, path: str | Path, approved: bool) -> None:
        self._require_approval(approved, f"cancellazione {path}")
        try:
            Path(path).expanduser().unlink()
        except OSError as exc:
            raise DeviceError(f"cancellazione fallita: {exc}") from exc

    def _authorized_path(
        self, path: str | Path, allowlist: Sequence[str]
    ) -> Path:
        """Percorso risolto e dentro l'allowlist, o errore esplicito."""
        candidate = Path(path).expanduser()
        try:
            candidate = candidate.resolve()
        except OSError as exc:
            raise DeviceError(f"percorso non risolvibile: {exc}") from exc
        if not _in_allowlist(candidate, allowlist):
            raise GateError(f"lettura fuori allowlist: {candidate}")
        return candidate

    def _termux_json(self, command: str) -> dict[str, Any]:
        result = self._execute([command])
        stdout = result.stdout or ""
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise DeviceError(f"output non JSON da {command}") from exc
        if not isinstance(payload, dict):
            raise DeviceError(f"output inatteso da {command}")
        return payload

    def _execute(self, cmd: list[str]) -> "subprocess.CompletedProcess[str]":
        logger.info("comando device", extra={"cmd": cmd})
        try:
            return self._run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise DeviceError(f"Termux:API o comando assente: {cmd[0]}") from exc
        except OSError as exc:
            raise DeviceError(f"esecuzione comando fallita: {exc}") from exc

    @staticmethod
    def _require_approval(approved: bool, action: str) -> None:
        if not approved:
            logger.warning("azione rifiutata dal gate", extra={"action": action})
            raise GateError(f"approvazione admin richiesta per: {action}")


def _in_allowlist(candidate: Path, allowlist: Sequence[str]) -> bool:
    for entry in allowlist:
        allowed = Path(entry).expanduser().resolve()
        if candidate == allowed or candidate.is_relative_to(allowed):
            return True
    return False
