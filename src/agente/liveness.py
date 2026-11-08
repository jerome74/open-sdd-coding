"""C-40 Liveness Scheduler — segnale di vita quotidiano (spec 11).

Il segnale parte alle ``limits.liveness_at`` (timezone del telefono) e va solo
all'amministratore tramite C-10. ``liveness_last_sent`` è scritto **solo** dopo
un invio riuscito: un fallimento resta rilevabile per assenza.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from .errors import AgenteError
from .notifications import NotificationService
from .storage.repositories import SettingsRepository

logger = logging.getLogger("agente.liveness")

LIVENESS_MARKER = "liveness_last_sent"


class LivenessScheduler:
    def __init__(
        self,
        notifications: NotificationService,
        settings: SettingsRepository,
        *,
        at: str = "08:00",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._notifications = notifications
        self._settings = settings
        self._at = _normalize_at(at)
        self._clock = clock or (lambda: datetime.now().astimezone())

    async def send_liveness(self) -> bool:
        """Invia il segnale; ``True`` solo se l'invio è riuscito."""
        text = f"✅ Segnale di vita: tutto ok ({self._at})."
        try:
            await self._notifications.alert_admin(text)
        except AgenteError as exc:
            logger.error(
                "segnale di vita non inviato",
                extra={"at": self._at, "error": type(exc).__name__},
            )
            return False
        moment = self._now()
        self._settings.set(
            LIVENESS_MARKER, moment.isoformat(timespec="seconds")
        )
        logger.info(
            "segnale di vita inviato",
            extra={"at": self._at, "sent_at": moment.isoformat(timespec="seconds")},
        )
        return True

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            now = now.astimezone()
        return now


def _normalize_at(value: str) -> str:
    parts = value.strip().split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"orario liveness non valido: {value}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"orario liveness non valido: {value}")
    return f"{hour:02d}:{minute:02d}"


__all__ = ["LIVENESS_MARKER", "LivenessScheduler"]
