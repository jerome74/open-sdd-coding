"""C-39 Boot Recovery — sequenza di avvio e riepilogo (spec 11).

All'avvio l'agente calcola il periodo di assenza, rileva il segnale di vita
mancato, carica i job in pausa, sincronizza i marcatori, recupera le occorrenze
mancate con C-19 e solo allora riattiva lo scheduler. Il wake-lock e
l'autostart restano nello script di boot (V-01): qui non si parla con C-07.

L'ordine è fissato dal piano 11: periodo e segnale sono calcolati all'ingresso,
prima di qualsiasi effetto sullo scheduler, così il job delle 8:00 non può
correre con il rilevamento.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from .device_monitor import LAST_ONLINE_AT
from .errors import AgenteError
from .liveness import LIVENESS_MARKER
from .recovery import RecoveryHandler
from .schedule_registrar import ScheduleRegistrar
from .scheduler import TaskScheduler
from .storage.repositories import SettingsRepository, TaskRepository

logger = logging.getLogger("agente.boot")

LAST_START_AT = "last_start_at"


@dataclass(frozen=True)
class OfflinePeriod:
    """Periodo senza contatto dell'agente (processo fermo e/o rete assente)."""

    since: datetime
    until: datetime
    seconds: int


@dataclass(frozen=True)
class RecoverySummary:
    """Esito dell'avvio (spec 11, C-39)."""

    missed_count: int
    recovered: int
    offline_period: OfflinePeriod | None
    liveness_missed: bool


class BootRecovery:
    def __init__(
        self,
        *,
        scheduler: TaskScheduler,
        registrar: ScheduleRegistrar,
        tasks: TaskRepository,
        recovery: RecoveryHandler,
        settings: SettingsRepository,
        liveness_at: str = "08:00",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._registrar = registrar
        self._tasks = tasks
        self._recovery = recovery
        self._settings = settings
        self._liveness_hour, self._liveness_minute = _parse_at(liveness_at)
        self._clock = clock or (lambda: datetime.now().astimezone())

    async def on_start(self) -> RecoverySummary:
        """Ripristina lo stato, recupera le occorrenze e riattiva i job."""
        now = self._now()
        previous = self._read_marker(LAST_START_AT, now)
        last_online = self._read_marker(LAST_ONLINE_AT, now)

        offline_period: OfflinePeriod | None = None
        liveness_missed = False
        if previous is not None:
            since = last_online if last_online is not None else previous
            offline_period = OfflinePeriod(
                since=since,
                until=now,
                seconds=max(0, int((now - since).total_seconds())),
            )
            liveness_missed = self._liveness_missed(now, previous)

        self._scheduler.start(paused=True)
        self._registrar.sync(self._tasks.list("active"))
        try:
            await self._recovery.recover_missed()
        except AgenteError:
            # V-13: il retry è il riavvio esterno; il marcatore resta vecchio.
            logger.exception("avvio parziale: recupero fallito")
            raise
        stats = self._recovery.last_summary
        self._scheduler.resume()
        self._settings.set(LAST_START_AT, now.isoformat(timespec="seconds"))

        summary = RecoverySummary(
            missed_count=stats.missed,
            recovered=stats.recovered,
            offline_period=offline_period,
            liveness_missed=liveness_missed,
        )
        logger.info(
            "avvio completato",
            extra={
                "offline_s": offline_period.seconds if offline_period else None,
                "missed": summary.missed_count,
                "recovered": summary.recovered,
                "liveness_missed": summary.liveness_missed,
            },
        )
        return summary

    # --- interni ----------------------------------------------------------

    def _liveness_missed(self, now: datetime, previous: datetime) -> bool:
        raw = self._settings.get(LIVENESS_MARKER)
        sent: datetime | None = None
        if raw is not None:
            sent = _parse(raw)
            if sent is None or sent > now:
                logger.warning(
                    "marcatore liveness non valido", extra={"value": raw}
                )
                sent = None
        due = last_liveness_due(
            now, self._liveness_hour, self._liveness_minute
        )
        if due is None or due < previous:
            return False
        return sent is None or sent < due

    def _read_marker(self, key: str, now: datetime) -> datetime | None:
        raw = self._settings.get(key)
        if raw is None:
            return None
        moment = _parse(raw)
        if moment is None or moment > now:
            logger.warning("marcatore non valido", extra={"key": key, "value": raw})
            return None
        return moment

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            now = now.astimezone()
        return now


def last_liveness_due(
    now: datetime, hour: int, minute: int
) -> datetime | None:
    """Ultima occorrenza di ``hour:minute`` ≤ now, nel fuso di ``now``."""
    if now.tzinfo is None:
        return None
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate > now:
        candidate -= timedelta(days=1)
    return candidate


def _parse(value: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _parse_at(value: str) -> tuple[int, int]:
    parts = value.strip().split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"orario liveness non valido: {value}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"orario liveness non valido: {value}")
    return hour, minute


__all__ = [
    "BootRecovery",
    "LAST_START_AT",
    "OfflinePeriod",
    "RecoverySummary",
    "last_liveness_due",
]
