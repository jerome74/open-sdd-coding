"""C-15 Task Manager — CRUD e validazione dei compiti (spec 02).

Nessuna scrittura avviene senza conferma esplicita (BR-1): la conferma è di
C-17 e il manager riceve solo operazioni già confermate. L'accesso è riservato
all'amministratore (BR-12); i destinatari sono utenti autorizzati e l'admin è
sempre destinatario. Il limite di compiti attivi è quello dichiarato (BR-16).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Callable, Sequence

from .errors import AgenteError, StorageError
from .role_guard import Role
from .schedule_registrar import ScheduleRegistrar
from .schedule_interpreter import (
    INTERVALLO,
    Schedule,
    ScheduleError,
    interval_minutes,
    validate_expr,
)
from .storage.repositories import (
    SubscriptionRepository,
    Task,
    TaskRepository,
    UserRepository,
)

logger = logging.getLogger("agente.tasks")

# BR-16: fino a 10 compiti attivi.
MAX_ACTIVE_TASKS = 10


class TaskValidationError(AgenteError):
    """Compito rifiutato dalla validazione: nessuna modifica applicata."""


@dataclass(frozen=True)
class TaskDraft:
    """Bozza di un compito, già riepilogata e confermata dall'admin."""

    name: str
    instructions: str
    schedule: Schedule
    recipients: tuple[int, ...] = ()
    log_allowlist: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskDelta:
    """Modifica parziale di un compito esistente."""

    name: str | None = None
    instructions: str | None = None
    schedule: Schedule | None = None
    recipients: tuple[int, ...] | None = None
    log_allowlist: tuple[str, ...] | None = None


@dataclass(frozen=True)
class TaskView:
    """Vista di elenco: compito e relativi destinatari."""

    task: Task
    recipients: tuple[int, ...] = field(default_factory=tuple)


class TaskManager:
    def __init__(
        self,
        tasks: TaskRepository,
        subscriptions: SubscriptionRepository,
        users: UserRepository,
        registrar: ScheduleRegistrar,
        *,
        admin_id: int,
        min_interval_minutes: int = 1,
        max_active_tasks: int = MAX_ACTIVE_TASKS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._tasks = tasks
        self._subscriptions = subscriptions
        self._users = users
        self._registrar = registrar
        self._admin_id = admin_id
        self._min_interval_minutes = max(1, int(min_interval_minutes))
        self._max_active_tasks = max(1, int(max_active_tasks))
        self._clock = clock or (lambda: datetime.now().astimezone())

    # --- lettura -----------------------------------------------------------

    def find(self, name: str) -> Task | None:
        """Ricerca per nome senza distinzione di maiuscole (D3).

        Il confronto è applicativo (``str.casefold``), perché SQLite ``NOCASE``
        copre solo l'ASCII; l'indice univoco ``NOCASE`` resta come rete di
        sicurezza sul database.
        """
        cleaned = name.strip()
        if not cleaned:
            return None
        exact = self._tasks.get_by_name(cleaned)
        if exact is not None:
            return exact
        folded = cleaned.casefold()
        for task in self._tasks.list():
            if task.name.casefold() == folded:
                return task
        return None

    def get(self, task_id: int) -> Task | None:
        return self._tasks.get(task_id)

    def list(self, role: Role, user_id: int) -> list[TaskView]:
        """Admin: tutti i compiti. Utente autorizzato: quelli a cui è iscritto."""
        if role is Role.ADMIN:
            tasks = self._tasks.list()
        elif role is Role.AUTHORIZED:
            tasks = [
                task
                for task in (self._tasks.get(task_id) for task_id in self._subscriptions.tasks_for_user(user_id))
                if task is not None
            ]
        else:
            return []
        return [
            TaskView(task=task, recipients=self._view_recipients(task.id))
            for task in tasks
        ]

    def active_count(self) -> int:
        return len(self._tasks.list("active"))

    # --- scrittura (dopo conferma) ----------------------------------------

    def create(self, draft: TaskDraft) -> Task:
        name = _require_text(draft.name, "nome")
        instructions = _require_text(draft.instructions, "istruzioni")
        schedule = self._validate_schedule(draft.schedule)
        if self.find(name) is not None:
            raise TaskValidationError(
                f"esiste già un compito chiamato «{name}»: scegli un altro nome."
            )
        if self.active_count() >= self._max_active_tasks:
            raise TaskValidationError(
                f"limite di {self._max_active_tasks} compiti attivi raggiunto (BR-16): "
                "sospendi o elimina un compito."
            )
        recipients = self._validated_recipients(draft.recipients)
        allowlist = _validated_allowlist(draft.log_allowlist)

        task = self._tasks.create(
            Task(
                name=name,
                instructions=instructions,
                schedule_type=schedule.type,
                schedule_expr=schedule.expr,
                state="active",
                log_allowlist=list(allowlist),
                created_by=self._admin_id,
            )
        )
        assert task.id is not None
        self._set_recipients(task.id, recipients)
        try:
            self._schedule(task)
        except Exception:
            # Nessuno stato parziale: il compito non deve restare senza job.
            self._tasks.delete(task.id)
            raise
        logger.info(
            "compito creato",
            extra={"task_id": task.id, "schedule_type": task.schedule_type},
        )
        return task

    def update(self, task_id: int, delta: TaskDelta) -> Task:
        task = self._require(task_id)
        if delta.name is not None:
            new_name = _require_text(delta.name, "nome")
            other = self.find(new_name)
            if other is not None and other.id != task.id:
                raise TaskValidationError(
                    f"esiste già un compito chiamato «{new_name}»."
                )
            task.name = new_name
        if delta.instructions is not None:
            task.instructions = _require_text(delta.instructions, "istruzioni")
        if delta.schedule is not None:
            schedule = self._validate_schedule(delta.schedule)
            task.schedule_type = schedule.type
            task.schedule_expr = schedule.expr
        if delta.log_allowlist is not None:
            task.log_allowlist = list(_validated_allowlist(delta.log_allowlist))

        if delta.recipients is not None:
            recipients = self._validated_recipients(delta.recipients)
        else:
            recipients = tuple(self._recipients(task.id))

        try:
            updated = self._tasks.update(task)
            if delta.recipients is not None:
                self._set_recipients(task.id, recipients)
            if updated.state == "active" and delta.schedule is not None:
                self._schedule(updated, update=True)
        except StorageError:
            raise
        logger.info("compito aggiornato", extra={"task_id": task_id})
        return updated

    def rename(self, task_id: int, new_name: str) -> Task:
        return self.update(task_id, TaskDelta(name=new_name))

    def pause(self, task_id: int) -> Task:
        task = self._require(task_id)
        self._tasks.set_state(task_id, "paused")
        self._registrar.unregister(task_id)
        logger.info("compito sospeso", extra={"task_id": task_id})
        task.state = "paused"
        return task

    def resume(self, task_id: int) -> Task:
        task = self._require(task_id)
        if task.state != "active" and self.active_count() >= self._max_active_tasks:
            raise TaskValidationError(
                f"limite di {self._max_active_tasks} compiti attivi raggiunto (BR-16): "
                "sospendi o elimina un compito."
            )
        self._tasks.set_state(task_id, "active")
        task.state = "active"
        self._schedule(task)
        logger.info("compito riattivato", extra={"task_id": task_id})
        return task

    def delete(self, task_id: int) -> None:
        self._require(task_id)
        self._registrar.unregister(task_id)
        self._tasks.delete(task_id)
        logger.info("compito eliminato", extra={"task_id": task_id})

    # --- interni -----------------------------------------------------------

    def _require(self, task_id: int) -> Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskValidationError("compito non trovato.")
        return task

    def _validate_schedule(self, schedule: Schedule) -> Schedule:
        try:
            validated = validate_expr(schedule.type, schedule.expr)
        except ScheduleError as exc:
            raise TaskValidationError(str(exc)) from exc
        minutes = interval_minutes(validated)
        if validated.type == INTERVALLO and minutes is not None:
            if minutes < self._min_interval_minutes:
                raise TaskValidationError(
                    f"intervallo troppo breve: minimo {self._min_interval_minutes} minuto/i."
                )
        return replace(validated, tz=schedule.tz)

    def _validated_recipients(self, recipients: Sequence[int]) -> tuple[int, ...]:
        unique = []
        for recipient in recipients:
            if recipient in unique:
                continue
            if recipient == self._admin_id:
                unique.append(recipient)
                continue
            user = self._users.get(recipient)
            if user is None or user.state != "accepted":
                raise TaskValidationError(
                    f"destinatario non autorizzato: {recipient}."
                )
            unique.append(recipient)
        if self._admin_id not in unique:
            unique.insert(0, self._admin_id)
        return tuple(unique)

    def _set_recipients(self, task_id: int, recipients: Sequence[int]) -> None:
        """Persistisce le iscrizioni degli utenti; l'admin non è un record utente.

        L'admin è sempre destinatario per spec, ma non ha una riga in ``users``
        (constitution, decisione #7): resta implicito e non viene iscritto.
        """
        current = set(self._recipients(task_id))
        wanted = {user_id for user_id in recipients if user_id != self._admin_id}
        for user_id in current - wanted:
            self._subscriptions.remove(user_id, task_id)
        for user_id in wanted - current:
            self._subscriptions.add(user_id, task_id)

    def _recipients(self, task_id: int) -> list[int]:
        return self._subscriptions.users_for_task(task_id)

    def _view_recipients(self, task_id: int) -> tuple[int, ...]:
        stored = [user_id for user_id in self._recipients(task_id) if user_id != self._admin_id]
        return (self._admin_id, *stored)

    def _schedule(self, task: Task, *, update: bool = False) -> None:
        if update:
            self._registrar.update(task)
        else:
            self._registrar.register(task)


def _require_text(value: str, label: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise TaskValidationError(f"campo mancante: {label}.")
    return cleaned


def _validated_allowlist(paths: Sequence[str]) -> tuple[str, ...]:
    cleaned: list[str] = []
    for path in paths:
        text = (path or "").strip()
        if not text:
            raise TaskValidationError("percorso di log vuoto nell'allowlist.")
        cleaned.append(text)
    return tuple(cleaned)
