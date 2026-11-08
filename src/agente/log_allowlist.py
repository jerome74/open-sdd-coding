"""C-30 Allowlist Validator — autorizzazione dei percorsi di log (spec 07).

BR-13: l'agente legge log solo da file o cartelle autorizzati dall'amministratore
alla creazione del compito. La policy vive qui; C-07 applica un controllo proprio
come ultima barriera dell'adapter.

La normalizzazione avviene **prima** del confronto: ``expanduser`` (così ``~/log``
è ammesso) e ``resolve`` (così ``..`` e i symlink non aggirano l'allowlist). Sono
autorizzati solo i percorsi assoluti: con un percorso relativo la base sarebbe la
directory di lavoro del processo, non una scelta dell'amministratore.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol, Sequence, Union

logger = logging.getLogger("agente.log_allowlist")

PathLike = Union[str, Path]


class HasLogAllowlist(Protocol):
    """Qualunque contesto con un'allowlist: un compito o il contesto di chat."""

    log_allowlist: Sequence[str]


class AllowlistValidator:
    def is_allowed(self, path: PathLike, task: HasLogAllowlist) -> bool:
        """Vero se ``path`` è dentro l'allowlist del compito (dopo normalizzazione)."""
        candidate = normalize_path(path)
        if candidate is None:
            logger.info(
                "percorso log rifiutato",
                extra={"path": _text(path), "reason": "percorso non valido"},
            )
            return False

        roots = [
            normalized
            for entry in (getattr(task, "log_allowlist", ()) or ())
            if (normalized := normalize_path(entry)) is not None
        ]
        allowed = any(is_within(candidate, root) for root in roots)
        logger.info(
            "validazione percorso log",
            extra={"path": str(candidate), "allowed": allowed, "roots": len(roots)},
        )
        return allowed


def normalize_path(value: PathLike | None) -> Path | None:
    """Percorso assoluto e risolto, oppure ``None`` se non è autorizzabile."""
    if not isinstance(value, (str, Path)):
        return None
    text = str(value).strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        return None
    try:
        return candidate.resolve()
    except OSError:
        return None


def is_within(candidate: Path, root: Path) -> bool:
    """``candidate`` è ``root`` o sta sotto ``root`` (entrambi già risolti)."""
    if candidate == root:
        return True
    try:
        return candidate.is_relative_to(root)
    except ValueError:
        return False


def _text(value: object) -> str:
    return value if isinstance(value, str) else str(value)
