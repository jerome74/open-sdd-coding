"""C-11 History & Retention — storico esecuzioni, retention, reset chat."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .errors import StorageError
from .storage.repositories import (
    ConversationRepository,
    Execution,
    ExecutionRepository,
)

logger = logging.getLogger("agente.history")


def _utc(value: str) -> str:
    """Converte un istante ISO nel formato UTC persistito (V-10).

    Un valore senza fuso è interpretato come UTC, come fanno SQLite e il
    resto dello storage; l'offset locale di C-19 viene invece convertito.
    """
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class PurgeStats:
    executions_deleted: int
    messages_deleted: int


class HistoryService:
    def __init__(
        self,
        executions: ExecutionRepository,
        conversations: ConversationRepository,
        *,
        retention_days: int,
        chat_memory_hours: int,
        clock: Any = None,
    ) -> None:
        self._executions = executions
        self._conversations = conversations
        self._retention_days = retention_days
        self._chat_memory_hours = chat_memory_hours
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def record(
        self,
        *,
        task_id: int,
        trigger: str,
        requested_by: int | None,
        started_at: str,
    ) -> Execution:
        return self._executions.create(
            Execution(
                task_id=task_id,
                trigger=trigger,
                requested_by=requested_by,
                started_at=_utc(started_at),
            )
        )

    def finish(
        self, execution_id: int, *, outcome: str, summary: str | None
    ) -> None:
        self._executions.finish(
            execution_id,
            finished_at=_utc(self._clock().isoformat(timespec="seconds")),
            outcome=outcome,
            summary=summary,
        )

    def record_skipped(
        self, *, task_id: int, occurred_at: str, note: str | None = None
    ) -> Execution:
        """Marcatura di un'occorrenza saltata (spec 03 C-19, esito ``saltata``).

        ``started_at`` e ``finished_at`` coincidono con l'istante dell'occorrenza
        mancata: l'esecuzione non è avvenuta, la riga serve allo storico (FR-008).
        """
        moment = _utc(occurred_at)
        execution = self._executions.create(
            Execution(
                task_id=task_id,
                trigger="scheduled",
                requested_by=None,
                started_at=moment,
            )
        )
        if execution.id is None:
            raise StorageError("occorrenza saltata non registrata")
        self._executions.finish(
            execution.id,
            finished_at=moment,
            outcome="saltata",
            summary=note or f"occorrenza saltata: {moment}",
        )
        return execution

    def query(
        self,
        *,
        user_id: int | None = None,
        since: str | None = None,
        until: str | None = None,
        task_id: int | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[Execution]:
        return self._executions.list(
            user_id=user_id,
            since=since,
            until=until,
            task_id=task_id,
            outcome=outcome,
            limit=limit,
        )

    def reset_conversation(self, user_id: int) -> None:
        now = self._utc_now()
        cutoff = (now - timedelta(hours=self._chat_memory_hours)).isoformat(
            timespec="seconds"
        )
        self._conversations.delete_messages_before_for_user(user_id, cutoff)

    def purge_expired(self) -> PurgeStats:
        now = self._utc_now()
        executions_cutoff = (now - timedelta(days=self._retention_days)).isoformat(
            timespec="seconds"
        )
        chat_cutoff = (now - timedelta(hours=self._chat_memory_hours)).isoformat(
            timespec="seconds"
        )
        executions_deleted = self._executions.delete_before(executions_cutoff)
        logger.info(
            "retention esecuzioni",
            extra={"deleted": executions_deleted, "cutoff": executions_cutoff},
        )
        messages_deleted = self._conversations.delete_messages_before(chat_cutoff)
        logger.info(
            "retention messaggi",
            extra={"deleted": messages_deleted, "cutoff": chat_cutoff},
        )
        return PurgeStats(
            executions_deleted=executions_deleted,
            messages_deleted=messages_deleted,
        )

    def _utc_now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)
