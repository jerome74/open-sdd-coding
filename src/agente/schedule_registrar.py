"""C-18 Schedule Registrar — registra i job dei compiti attivi (spec 03).

Traduce lo ``Schedule`` canonico (C-16) in un trigger APScheduler tramite C-06 e
persiste in ``settings`` il marcatore ``next_run:<task_id>`` usato da C-19 per il
recupero (BR-5). La meccanica dei job resta di C-06: qui c'è solo la politica di
registrazione, così C-15 non parla più direttamente con lo scheduler.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Iterable

from .schedule_interpreter import validate_expr
from .scheduler import TaskScheduler, trigger_for
from .storage.repositories import SettingsRepository, Task

logger = logging.getLogger("agente.schedule_registrar")

SETTING_PREFIX = "next_run:"


class ScheduleRegistrar:
    def __init__(
        self,
        settings: SettingsRepository,
        scheduler: TaskScheduler,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._scheduler = scheduler
        self._clock = clock or (lambda: datetime.now().astimezone())

    @staticmethod
    def setting_key(task_id: int) -> str:
        return f"{SETTING_PREFIX}{task_id}"

    def register(self, task: Task) -> str:
        """Registra il job di un compito nuovo o riattivato."""
        job_id = self._add(task)
        logger.info(
            "job registrato",
            extra={"task_id": task.id, "job_id": job_id, "next_run": self.next_run(task.id)},
        )
        return job_id

    def update(self, task: Task) -> str:
        """Ri-registra il job dopo una modifica di schedulazione o un recupero."""
        job_id = self._add(task)
        logger.info(
            "job aggiornato",
            extra={"task_id": task.id, "job_id": job_id, "next_run": self.next_run(task.id)},
        )
        return job_id

    def unregister(self, task_id: int) -> None:
        """Rimuove il job e il marcatore di recupero (pausa o eliminazione)."""
        self._scheduler.unschedule_task(task_id)
        self._settings.delete(self.setting_key(task_id))
        logger.info("job annullato", extra={"task_id": task_id})

    def refresh(self, task_id: int) -> datetime | None:
        """Allinea il marcatore al ``next_run`` corrente del job."""
        moment = self._scheduler.next_run(task_id)
        key = self.setting_key(task_id)
        if moment is None:
            self._settings.delete(key)
            return None
        self._settings.set(key, moment.isoformat(timespec="seconds"))
        return moment

    def sync(self, tasks: Iterable[Task]) -> None:
        """Inizializza i marcatori dai job persistiti, senza ri-registrarli.

        All'avvio il job store contiene già i job (C-06): riscriverli
        cambierebbe l'ancora degli intervalli (piano 03, P-A-11).
        """
        for task in tasks:
            if task.id is None:
                continue
            self.refresh(task.id)

    def next_run(self, task_id: int) -> datetime | None:
        """Marcatore persistito: ``None`` se assente o illeggibile."""
        raw = self._settings.get(self.setting_key(task_id))
        if not raw:
            return None
        try:
            moment = datetime.fromisoformat(raw)
        except ValueError:
            logger.warning(
                "marcatore next_run illeggibile",
                extra={"task_id": task_id, "value": raw},
            )
            return None
        return moment if moment.tzinfo is not None else moment.astimezone()

    def _add(self, task: Task) -> str:
        if task.id is None:
            raise ValueError("compito senza id: impossibile schedulare")
        schedule = validate_expr(task.schedule_type, task.schedule_expr)
        trigger = trigger_for(schedule, start=self._clock())
        try:
            job_id = self._scheduler.schedule_task(task, trigger)
            self.refresh(task.id)
        except Exception:
            # Nessuno stato parziale: job e marcatore non devono restare orfani.
            self._scheduler.unschedule_task(task.id)
            self._settings.delete(self.setting_key(task.id))
            raise
        return job_id
