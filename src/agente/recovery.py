"""C-19 Recovery Handler — recupero delle occorrenze mancate (spec 03).

Semantica BR-5 / decisione #8: si esegue **una sola volta** l'ultima occorrenza
mancata; le precedenti sono registrate come ``saltata`` (D1, migrazione 003).

Il marcatore ``next_run:<task_id>`` è scritto da C-18 e avanzato solo dopo
un'esecuzione: finché resta nel passato, l'occorrenza è da recuperare. Questo
rende il recupero idempotente e impedisce il doppio recupero con il boot di
spec 11, che dovrà delegare a questo componente.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .device_monitor import OFFLINE_SINCE, DeviceMonitor
from .errors import AgenteError, LockHeldError
from .execution import ExecutionEngine, ExecutionResult
from .history import HistoryService
from .schedule_interpreter import validate_expr
from .schedule_registrar import ScheduleRegistrar
from .scheduler import trigger_for
from .storage.repositories import Task, TaskRepository

logger = logging.getLogger("agente.recovery")


# P-A-03: tetto di sicurezza sul calcolo delle occorrenze mancate.
MAX_OCCURRENCES = 1000


@dataclass(frozen=True)
class RecoveryStats:
    """Conteggi dell'ultimo recupero (spec 11, additivo)."""

    missed: int = 0
    recovered: int = 0
    failed: int = 0
    skipped: int = 0
    deferred: int = 0


class RecoveryHandler:
    def __init__(
        self,
        *,
        tasks: TaskRepository,
        registrar: ScheduleRegistrar,
        engine: ExecutionEngine,
        history: HistoryService,
        monitor: DeviceMonitor,
        clock: Callable[[], datetime] | None = None,
        max_occurrences: int = MAX_OCCURRENCES,
    ) -> None:
        self._tasks = tasks
        self._registrar = registrar
        self._engine = engine
        self._history = history
        self._monitor = monitor
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._max_occurrences = max(1, int(max_occurrences))
        self._last_summary = RecoveryStats()

    @property
    def last_summary(self) -> RecoveryStats:
        """Conteggi dell'ultimo recupero (spec 11, C-39 li legge)."""
        return self._last_summary

    # --- watcher di connettività -----------------------------------------

    async def check_connectivity(self) -> list[ExecutionResult]:
        """Job periodico: C-37 aggiorna lo stato, C-19 recupera al rientro."""
        self._last_summary = RecoveryStats()
        status = await self._monitor.check_online()
        if status.online is not True:
            return []
        if status.resumed:
            logger.info("rientro online: avvio recupero")
            return await self._recover(self._clock())
        return []

    # --- recupero ---------------------------------------------------------

    async def recover_missed(self) -> list[ExecutionResult]:
        """Recupera le occorrenze mancate dei compiti attivi (una sola volta)."""
        self._last_summary = RecoveryStats()
        if await self._monitor.is_online() is not True:
            logger.info("recupero rinviato: rete assente")
            return []
        return await self._recover(self._clock())

    async def _recover(self, now: datetime) -> list[ExecutionResult]:
        if now.tzinfo is None:
            now = now.astimezone()
        results: list[ExecutionResult] = []
        recovered = failed = skipped_count = deferred = 0
        for task in self._tasks.list("active"):
            if task.id is None:
                continue
            marker = self._registrar.next_run(task.id)
            if marker is None:
                continue
            occurrences = self._occurrences(task, marker, now)
            if not occurrences:
                continue
            skipped = occurrences[:-1]
            last = occurrences[-1]
            for when in skipped:
                occurred_at = when.isoformat(timespec="seconds")
                self._history.record_skipped(
                    task_id=task.id,
                    occurred_at=occurred_at,
                    note=f"occorrenza saltata: {occurred_at}",
                )
                skipped_count += 1
            logger.info(
                "recupero occorrenza",
                extra={
                    "task_id": task.id,
                    "occurrence": last.isoformat(timespec="seconds"),
                    "skipped": len(skipped),
                },
            )
            try:
                result = await self._engine.execute(task, "recovery")
            except LockHeldError:
                # Un'esecuzione è già in corso: l'occorrenza è coperta da quella
                # (spec 04 C-22); il marcatore va comunque avanzato.
                deferred += 1
                logger.info(
                    "recupero rinviato: esecuzione in corso",
                    extra={"task_id": task.id},
                )
                continue
            finally:
                # Marcatore e job riallineati subito: un secondo recupero non
                # deve rivedere la stessa occorrenza (idempotenza).
                self._registrar.update(task)
            results.append(result)
            if result.outcome == "ok":
                recovered += 1
            else:
                failed += 1
        self._last_summary = RecoveryStats(
            missed=recovered + failed + skipped_count + deferred,
            recovered=recovered,
            failed=failed,
            skipped=skipped_count,
            deferred=deferred,
        )
        return results

    def _occurrences(
        self, task: Task, marker: datetime, now: datetime
    ) -> list[datetime]:
        try:
            schedule = validate_expr(task.schedule_type, task.schedule_expr)
        except AgenteError as exc:
            logger.warning(
                "recupero impossibile: schedulazione non valida",
                extra={"task_id": task.id, "error": str(exc)},
            )
            return []
        trigger = trigger_for(schedule, start=marker)
        occurrences: list[datetime] = []
        cursor = trigger.get_next_fire_time(None, marker)
        while cursor is not None and cursor <= now and len(occurrences) < self._max_occurrences:
            occurrences.append(cursor)
            following = trigger.get_next_fire_time(cursor, cursor)
            if following is None or following <= cursor:
                break
            cursor = following
        if len(occurrences) >= self._max_occurrences:
            logger.warning(
                "occorrenze mancate troncate al tetto",
                extra={"task_id": task.id, "max": self._max_occurrences},
            )
        return occurrences

