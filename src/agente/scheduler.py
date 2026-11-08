"""C-06 Scheduler — job dei compiti e manutenzione, store persistente.

L'interpretazione di ``schedule_type``/``schedule_expr`` è di spec 02 (C-16):
qui il chiamante fornisce un trigger APScheduler già costruito. Così la
fondazione non inventa una sintassi di schedulazione.
"""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
from typing import Any, Callable

from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .errors import AgenteError
from .schedule_interpreter import (
    ORARIO,
    Schedule,
    hour_minute,
    interval_minutes,
    weekdays,
)
from .storage.repositories import Task

logger = logging.getLogger("agente.scheduler")

_DISPATCHER: Callable[[int], Any] | None = None
_MAINTENANCE: Callable[[], Any] | None = None
_CONNECTIVITY: Callable[[], Any] | None = None
_BATTERY: Callable[[], Any] | None = None
_LIVENESS: Callable[[], Any] | None = None

MAINTENANCE_JOB_ID = "maintenance:purge"
CONNECTIVITY_JOB_ID = "connectivity:check"
BATTERY_JOB_ID = "battery:check"
LIVENESS_JOB_ID = "liveness:send"

# APScheduler usa i nomi inglesi dei giorni; la spec 02 usa le abbreviazioni
# italiane nell'espressione canonica.
_DAY_OF_WEEK = {
    "LUN": "mon",
    "MAR": "tue",
    "MER": "wed",
    "GIO": "thu",
    "VEN": "fri",
    "SAB": "sat",
    "DOM": "sun",
}


def trigger_for(schedule: Schedule, *, start: Any = None) -> BaseTrigger:
    """Traduce una schedulazione canonica (C-16) in trigger APScheduler.

    La timezone non è forzata: lo scheduler usa quella del telefono (BR-14).
    Gli intervalli sono ancorati all'istante di registrazione del job (piano 02
    D1): ``start`` è l'istante di creazione, o di riattivazione con ``/resume``.
    """
    if schedule.type == ORARIO:
        hour, minute = hour_minute(schedule)
        days = weekdays(schedule)
        return CronTrigger(
            hour=hour,
            minute=minute,
            day_of_week=",".join(_DAY_OF_WEEK[day] for day in days) if days else None,
        )
    minutes = interval_minutes(schedule)
    if minutes is None:
        raise SchedulerError("intervallo non valido")
    return IntervalTrigger(minutes=minutes, start_date=start)


async def _run_scheduled_job(task_id: int) -> Any:
    """Entry point serializzabile nello job store (deve restare module-level).

    È una coroutine function: ``AsyncIOScheduler`` la esegue nell'event loop
    invece di scartarne il valore di ritorno.
    """
    if _DISPATCHER is None:
        logger.warning("job senza dispatcher", extra={"task_id": task_id})
        return None
    return await _DISPATCHER(task_id)


async def _run_maintenance_job() -> Any:
    """Job giornaliero di manutenzione: retention e reset chat (C-11, C-24).

    È una coroutine function: ``AsyncIOScheduler`` la esegue nell'event loop,
    dove vive la connessione SQLite (``check_same_thread=True``). Un callback
    sincrono viene invocato qui; uno asincrono viene atteso.
    """
    if _MAINTENANCE is None:
        logger.warning("manutenzione senza callback")
        return None
    result = _MAINTENANCE()
    if inspect.isawaitable(result):
        return await result
    return result


async def _run_connectivity_job() -> Any:
    """Job di verifica rete: rientro online → recupero occorrenze (C-19)."""
    if _CONNECTIVITY is None:
        logger.warning("connettività senza callback")
        return None
    return await _CONNECTIVITY()


async def _run_liveness_job() -> Any:
    """Job quotidiano del segnale di vita (spec 11, C-40)."""
    if _LIVENESS is None:
        logger.warning("liveness senza callback")
        return None
    try:
        result = _LIVENESS()
        if inspect.isawaitable(result):
            return await result
        return result
    except Exception:  # noqa: BLE001 - un job in errore non ferma gli altri
        logger.exception("job liveness fallito")
        return None


async def _run_battery_job() -> Any:
    """Job periodico batteria: C-37 legge e C-36 decide l'avviso (spec 10)."""
    if _BATTERY is None:
        logger.warning("batteria senza callback")
        return None
    try:
        result = _BATTERY()
        if inspect.isawaitable(result):
            return await result
        return result
    except Exception:  # noqa: BLE001 - un job in errore non ferma gli altri
        logger.exception("job batteria fallito")
        return None


class SchedulerError(AgenteError):
    """Errore di schedulazione."""


def _parse_liveness_time(value: str) -> tuple[int, int]:
    """Guardia dell'API: C-01 è il validatore di merito di ``liveness_at``."""
    parts = value.strip().split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise SchedulerError("orario liveness non valido")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise SchedulerError("orario liveness non valido")
    return hour, minute


class TaskScheduler:
    def __init__(
        self,
        db_path: str | Path,
        *,
        scheduler: AsyncIOScheduler | Any | None = None,
        timezone: Any = None,
        dispatcher: Callable[[int], Any] | None = None,
    ) -> None:
        self._db_path = Path(db_path).expanduser()
        self._scheduler = scheduler or AsyncIOScheduler(
            jobstores={"default": SQLAlchemyJobStore(url=self._url())},
            timezone=timezone,
            job_defaults={"coalesce": True, "max_instances": 1},
        )
        self._dispatcher = dispatcher

    def _url(self) -> str:
        return f"sqlite:///{self._db_path}"

    def set_dispatcher(self, dispatcher: Callable[[int], Any]) -> None:
        global _DISPATCHER
        self._dispatcher = dispatcher
        _DISPATCHER = dispatcher

    def start(self, *, paused: bool = False) -> None:
        """Avvia lo scheduler; ``paused=True`` carica i job senza eseguirli.

        L'avvio in pausa serve a C-19: leggere i ``next_run`` persistiti e
        recuperare le occorrenze mancate prima che i job ripartano (spec 03).
        """
        self._scheduler.start(paused=paused)
        if self._dispatcher is not None:
            self.set_dispatcher(self._dispatcher)
        logger.info(
            "scheduler avviato",
            extra={
                "jobs": len(self._scheduler.get_jobs()),
                "db": str(self._db_path),
                "paused": paused,
            },
        )

    def resume(self) -> None:
        """Riattiva l'esecuzione dei job dopo un avvio in pausa."""
        self._scheduler.resume()
        logger.info("scheduler riattivato")

    def shutdown(self, wait: bool = False) -> None:
        self._scheduler.shutdown(wait=wait)

    def schedule_task(self, task: Task, trigger: BaseTrigger) -> str:
        if task.id is None:
            raise SchedulerError("compito senza id: impossibile schedulare")
        job_id = self.job_id(task.id)
        self._scheduler.add_job(
            _run_scheduled_job,
            trigger=trigger,
            args=[task.id],
            id=job_id,
            replace_existing=True,
            name=f"task:{task.name}",
            misfire_grace_time=None,
        )
        logger.info("job schedulato", extra={"task_id": task.id, "job_id": job_id})
        return job_id

    def schedule_maintenance(
        self, callback: Callable[[], Any], *, interval_hours: int = 24
    ) -> str:
        """Registra il job giornaliero di retention/reset chat.

        La spec dichiara un job giornaliero ma non un'ora: si usa un intervallo
        di 24 ore dall'avvio, senza inventare un orario fisso.
        """
        global _MAINTENANCE
        _MAINTENANCE = callback
        self._scheduler.add_job(
            _run_maintenance_job,
            trigger=IntervalTrigger(hours=interval_hours),
            id=MAINTENANCE_JOB_ID,
            replace_existing=True,
            name="manutenzione",
        )
        logger.info("job manutenzione schedulato", extra={"interval_hours": interval_hours})
        return MAINTENANCE_JOB_ID

    def schedule_connectivity(
        self, callback: Callable[[], Any], *, interval_s: int = 60
    ) -> str:
        """Registra il job periodico di verifica connettività (spec 03, D4).

        L'intervallo è ``limits.connectivity_check_s``: la spec 03 non dichiara
        un valore, il default è l'ultima parte della decisione D4.
        """
        global _CONNECTIVITY
        if interval_s <= 0:
            raise SchedulerError("intervallo di verifica rete non valido")
        _CONNECTIVITY = callback
        self._scheduler.add_job(
            _run_connectivity_job,
            trigger=IntervalTrigger(seconds=interval_s),
            id=CONNECTIVITY_JOB_ID,
            replace_existing=True,
            name="connettività",
        )
        logger.info("job connettività schedulato", extra={"interval_s": interval_s})
        return CONNECTIVITY_JOB_ID

    def schedule_liveness(
        self, callback: Callable[[], Any], *, at: str = "08:00"
    ) -> str:
        """Registra il job quotidiano del segnale di vita (spec 11, C-40)."""
        global _LIVENESS
        hour, minute = _parse_liveness_time(at)
        _LIVENESS = callback
        self._scheduler.add_job(
            _run_liveness_job,
            trigger=CronTrigger(
                hour=hour, minute=minute, timezone=self._scheduler.timezone
            ),
            id=LIVENESS_JOB_ID,
            replace_existing=True,
            name="liveness",
            misfire_grace_time=None,
        )
        logger.info("job liveness schedulato", extra={"at": at})
        return LIVENESS_JOB_ID

    def schedule_battery(
        self, callback: Callable[[], Any], *, interval_s: int = 300
    ) -> str:
        """Registra il job periodico di lettura batteria (spec 10, D2)."""
        global _BATTERY
        if interval_s <= 0:
            raise SchedulerError("intervallo di lettura batteria non valido")
        _BATTERY = callback
        self._scheduler.add_job(
            _run_battery_job,
            trigger=IntervalTrigger(seconds=interval_s),
            id=BATTERY_JOB_ID,
            replace_existing=True,
            name="batteria",
        )
        logger.info("job batteria schedulato", extra={"interval_s": interval_s})
        return BATTERY_JOB_ID

    def unschedule_task(self, task_id: int) -> None:
        try:
            self._scheduler.remove_job(self.job_id(task_id))
        except JobLookupError:
            logger.info("job già assente", extra={"task_id": task_id})
            return
        logger.info("job rimosso", extra={"task_id": task_id})

    def next_run(self, task_id: int) -> Any:
        job = self._scheduler.get_job(self.job_id(task_id))
        return None if job is None else job.next_run_time

    def jobs(self) -> list[Any]:
        return list(self._scheduler.get_jobs())

    @staticmethod
    def job_id(task_id: int) -> str:
        return f"task:{task_id}"
