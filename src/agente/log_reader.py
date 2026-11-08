"""C-29 Log Reader — legge i log consentiti e prepara il testo (spec 07).

Regole applicate qui, non delegate al modello:

- ogni percorso è autorizzato da C-30 prima di essere toccato (BR-13);
- l'accesso fisico passa solo da C-07 (coda limitata, metadati, elenco);
- un file inesistente, vuoto o illeggibile è **segnalato** nel risultato, non è
  un errore del compito;
- un percorso non autorizzato non viene letto, finisce in ``refused`` e nel
  testo reso: C-08 lo trasforma in ``LogAccessError``, C-09 avvisa l'admin;
- i file grandi sono troncati alla coda (P-A-02) e i limiti sono dichiarati nel
  testo, così il modello sa cosa non ha visto.

Nessun parsing: i log sono testo libero (D3). Anche le righe JSONL di C-13
restano testo leggibile.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Union

from .device import MAX_LOG_FILES, MAX_LOG_SLICE_CHARS, DeviceAdapter, PathInfo
from .errors import DeviceError, GateError
from .log_allowlist import AllowlistValidator, HasLogAllowlist

logger = logging.getLogger("agente.log_reader")

# P-A-02: tetto per chiamata, allineato a `gate.MAX_OUTPUT_CHARS` (test di
# uguaglianza, non import: C-29 non dipende da C-27).
MAX_TOTAL_CHARS = 20_000
# P-A-20: margine per i prefissi dei chiamanti ("errore dello strumento: ").
MAX_ERROR_PAYLOAD_CHARS = MAX_TOTAL_CHARS - 200
# Sotto questa soglia non vale la pena aprire un altro file (P-A-22).
MIN_REMAINING_CHARS = 500
# Spazio riservato alle note finali, che vengono accodate dopo i file.
NOTES_RESERVE = 300

PathLike = Union[str, Path]


@dataclass(frozen=True)
class LogEntry:
    """Un file esaminato: testo (eventualmente vuoto) e note."""

    path: str
    text: str
    exists: bool
    size: int
    truncated: bool
    note: str = ""


@dataclass(frozen=True)
class LogContent:
    """Esito di una lettura: file esaminati, rifiuti e note di cartella."""

    entries: tuple[LogEntry, ...]
    refused: tuple[str, ...]
    notes: tuple[str, ...]
    rendered: str


class _Allowlist:
    """Adattatore minimo: C-30 vuole un oggetto con ``log_allowlist``."""

    def __init__(self, roots: Sequence[str]) -> None:
        self.log_allowlist = tuple(roots)


class LogReader:
    def __init__(
        self,
        device: DeviceAdapter,
        *,
        validator: AllowlistValidator | None = None,
    ) -> None:
        self._device = device
        self._validator = validator or AllowlistValidator()

    def read(self, paths: Sequence[PathLike], allowlist: Sequence[str]) -> LogContent:
        """Legge i percorsi consentiti; i rifiuti non interrompono gli altri."""
        roots = tuple(allowlist or ())
        requested = list(paths or ())
        if not requested:
            return LogContent((), (), ("nessun percorso richiesto",), "Nessun percorso richiesto.")

        task: HasLogAllowlist = _Allowlist(roots)
        entries: list[LogEntry] = []
        refused: list[str] = []
        notes: list[str] = []
        parts: list[str] = []
        used = 0

        for index, raw in enumerate(requested):
            label = _label(raw)
            remaining_paths = len(requested) - index

            if not self._validator.is_allowed(raw, task):
                refused.append(label)
                parts.append(f"== PERCORSO NON AUTORIZZATO: {label} ==")
                logger.warning("percorso log rifiutato", extra={"path": label})
                continue

            try:
                info = self._device.inspect_path(raw, roots)
            except GateError:
                refused.append(label)
                parts.append(f"== PERCORSO NON AUTORIZZATO: {label} ==")
                notes.append(f"{label}: rifiutato dall'adapter")
                logger.warning("percorso log rifiutato dall'adapter", extra={"path": label})
                continue
            except DeviceError as exc:
                entry = LogEntry(label, "", False, 0, False, f"illeggibile: {exc}")
                entries.append(entry)
                parts.append(_header(entry))
                notes.append(f"{label}: {entry.note}")
                logger.info("ispezione log fallita", extra={"path": label, "error": str(exc)})
                continue

            if info.is_dir:
                used, stopped = self._collect_directory(
                    info, roots, remaining_paths, entries, notes, parts, used
                )
                if stopped:
                    break
                continue

            entry, used, stopped = self._collect_file(
                info, roots, entries, notes, parts, used, remaining_paths
            )
            if stopped:
                break

        rendered = "\n".join(parts + notes) if (parts or notes) else "Nessun contenuto."
        if len(rendered) > MAX_TOTAL_CHARS:
            suffix = "\n[output troncato]"
            rendered = rendered[: MAX_TOTAL_CHARS - len(suffix)] + suffix
            notes.append("output troncato al limite complessivo")
        logger.info(
            "lettura log conclusa",
            extra={
                "paths": len(requested),
                "entries": len(entries),
                "refused": len(refused),
            },
        )
        return LogContent(
            entries=tuple(entries),
            refused=tuple(refused),
            notes=tuple(notes),
            rendered=rendered,
        )

    # --- interni ----------------------------------------------------------

    def _collect_directory(
        self,
        info: PathInfo,
        roots: Sequence[str],
        remaining_paths: int,
        entries: list[LogEntry],
        notes: list[str],
        parts: list[str],
        used: int,
    ) -> tuple[int, bool]:
        try:
            listing = self._device.list_files(info.path, roots)
        except (GateError, DeviceError) as exc:
            notes.append(f"{info.path}: illeggibile: {exc}")
            logger.info("elenco log fallito", extra={"path": info.path, "error": str(exc)})
            return used, False

        if listing.truncated:
            notes.append(f"{info.path}: elenco troncato a {MAX_LOG_FILES} file")
        if listing.skipped_dirs:
            notes.append(f"{info.path}: sottocartelle ignorate: {listing.skipped_dirs}")
        if listing.skipped_links:
            notes.append(f"{info.path}: symlink ignorati: {listing.skipped_links}")
        if not listing.files:
            notes.append(f"{info.path}: cartella senza file")
            return used, False

        for position, file_path in enumerate(listing.files):
            try:
                file_info = self._device.inspect_path(file_path, roots)
            except (GateError, DeviceError) as exc:
                notes.append(f"{file_path}: illeggibile: {exc}")
                continue
            left = len(listing.files) - position - 1 + remaining_paths - 1
            entry, used, stopped = self._collect_file(
                file_info, roots, entries, notes, parts, used, max(1, left)
            )
            if stopped:
                return used, True
        return used, False

    def _collect_file(
        self,
        info: PathInfo,
        roots: Sequence[str],
        entries: list[LogEntry],
        notes: list[str],
        parts: list[str],
        used: int,
        remaining: int,
    ) -> tuple[LogEntry, int, bool]:
        estimated_header = len(info.path) + 60
        available = min(
            MAX_LOG_SLICE_CHARS,
            MAX_TOTAL_CHARS - used - estimated_header - NOTES_RESERVE,
        )
        if available < MIN_REMAINING_CHARS:
            notes.append(f"limite complessivo raggiunto: {remaining} file non letti")
            return LogEntry(info.path, "", info.exists, info.size, False, "non letto"), used, True

        if not info.exists:
            entry = LogEntry(info.path, "", False, 0, False, "file inesistente")
            entries.append(entry)
            parts.append(_header(entry))
            notes.append(f"{info.path}: file inesistente")
            return entry, used, False

        if not info.readable:
            entry = LogEntry(info.path, "", True, info.size, False, "illeggibile")
            entries.append(entry)
            parts.append(_header(entry))
            notes.append(f"{info.path}: illeggibile")
            return entry, used, False

        if info.size == 0:
            entry = LogEntry(info.path, "", True, 0, False, "file vuoto")
            entries.append(entry)
            parts.append(_header(entry))
            notes.append(f"{info.path}: file vuoto")
            return entry, used, False

        try:
            tail = self._device.read_file_tail(info.path, roots, max_chars=available)
        except GateError:
            entry = LogEntry(info.path, "", True, info.size, False, "rifiutato dall'adapter")
            notes.append(f"{info.path}: rifiutato dall'adapter")
            logger.warning("lettura log rifiutata", extra={"path": info.path})
        except DeviceError as exc:
            entry = LogEntry(info.path, "", True, info.size, False, f"illeggibile: {exc}")
            notes.append(f"{info.path}: illeggibile")
            logger.info("lettura log fallita", extra={"path": info.path, "error": str(exc)})
        else:
            entry = LogEntry(
                info.path,
                tail.text,
                True,
                tail.size,
                tail.truncated,
            )
            logger.info(
                "log letto",
                extra={
                    "path": info.path,
                    "size": tail.size,
                    "chars": len(tail.text),
                    "truncated": tail.truncated,
                },
            )

        entries.append(entry)
        block = _header(entry)
        if entry.text:
            block = f"{block}\n{entry.text}"
        parts.append(block)
        used = min(
            MAX_TOTAL_CHARS,
            used + len(block) + 1,
        )
        return entry, used, False


def _header(entry: LogEntry) -> str:
    if not entry.exists:
        return f"== {entry.path} (file inesistente) =="
    if entry.note:
        return f"== {entry.path} ({entry.size} byte; {entry.note}) =="
    suffix = "; troncato" if entry.truncated else ""
    return (
        f"== {entry.path} ({entry.size} byte; coda di "
        f"{len(entry.text)} caratteri{suffix}) =="
    )


def _label(value: object) -> str:
    return value if isinstance(value, str) else str(value)
