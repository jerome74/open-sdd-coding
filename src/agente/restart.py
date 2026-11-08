"""C-41 Restart Notifier — messaggio di ripartenza (spec 11).

Compone il messaggio con periodo di assenza e compiti recuperati e, quando
serve, la riga del segnale delle 8:00 non inviato. L'invio passa solo da C-10;
un fallimento è loggato e non solleva (BR-8 resta nel gateway C-03).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from .alerts import human_duration
from .boot import OfflinePeriod, RecoverySummary, last_liveness_due
from .errors import AgenteError
from .notifications import NotificationService

logger = logging.getLogger("agente.restart")


class RestartNotifier:
    def __init__(
        self,
        notifications: NotificationService,
        *,
        at: str = "08:00",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._notifications = notifications
        self._hour, self._minute = _parse_at(at)
        self._at = f"{self._hour:02d}:{self._minute:02d}"
        self._clock = clock or (lambda: datetime.now().astimezone())

    async def notify_restart(
        self,
        recovery_summary: RecoverySummary,
        offline_period: OfflinePeriod | None,
        liveness_missed: bool,
    ) -> bool:
        """Invia il messaggio di ripartenza; ``False`` se non inviato."""
        if offline_period is None:
            logger.info("ripartenza non inviata: nessun avvio precedente")
            return False

        text = self._compose(recovery_summary, offline_period, liveness_missed)
        try:
            await self._notifications.alert_admin(text)
        except AgenteError as exc:
            logger.error(
                "ripartenza non inviata",
                extra={"error": type(exc).__name__},
            )
            return False
        logger.info(
            "ripartenza inviata",
            extra={
                "offline_s": offline_period.seconds,
                "recovered": recovery_summary.recovered,
                "missed": recovery_summary.missed_count,
            },
        )
        return True

    def _compose(
        self,
        summary: RecoverySummary,
        period: OfflinePeriod,
        liveness_missed: bool,
    ) -> str:
        since = period.since.astimezone()
        until = period.until.astimezone()
        count = summary.recovered
        verb = "recuperato" if count == 1 else "recuperati"
        tasks = "compito" if count == 1 else "compiti"
        lines = [
            "🔄 Sono di nuovo attivo — "
            f"offline dalle {since:%d/%m %H:%M} alle {until:%d/%m %H:%M} "
            f"({human_duration(period.seconds)}), {verb} {count} {tasks}."
        ]
        if liveness_missed:
            due = last_liveness_due(period.until, self._hour, self._minute)
            if due is not None and period.since <= due <= period.until:
                lines.append(
                    f"⏰ Segnale delle {self._at} non inviato — "
                    f"offline dalle {since:%d/%m %H:%M} "
                    f"alle {until:%d/%m %H:%M}."
                )
            else:
                lines.append(f"⏰ Segnale delle {self._at} non inviato.")
        return "\n".join(lines)


def _parse_at(value: str) -> tuple[int, int]:
    parts = value.strip().split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"orario liveness non valido: {value}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"orario liveness non valido: {value}")
    return hour, minute


__all__ = ["RestartNotifier"]
