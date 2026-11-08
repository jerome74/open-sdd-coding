"""C-21: permessi, iscrizioni e rifiuti del lancio manuale (spec 04)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agente.errors import LockHeldError, RunRefused
from agente.execution import ExecutionResult
from agente.role_guard import Role
from agente.run_dispatcher import RunDispatcher
from agente.schedule_interpreter import Schedule
from agente.storage.db import Database
from agente.storage.repositories import Task, User, repositories
from agente.task_manager import TaskDraft, TaskManager

ADMIN = 1
USER = 2
REVOKED = 3


class FakeRegistrar:
    def __init__(self) -> None:
        self.scheduled: list[int] = []
        self.unscheduled: list[int] = []

    def register(self, task):
        self.scheduled.append(task.id)
        return f"task:{task.id}"

    def update(self, task):
        self.scheduled.append(task.id)
        return f"task:{task.id}"

    def unregister(self, task_id: int) -> None:
        self.unscheduled.append(task_id)


class FakeExecution:
    """C-09 finto: registra gli invocchi e restituisce un esito controllabile."""

    def __init__(self, error: Exception | None = None, outcome: str = "ok") -> None:
        self.calls: list[tuple[int, str, int | None]] = []
        self.error = error
        self.outcome = outcome

    async def execute(self, task, trigger: str, requester=None) -> ExecutionResult:
        self.calls.append((task.id, trigger, requester))
        if self.error is not None:
            raise self.error
        moment = datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc).isoformat()
        return ExecutionResult(
            execution_id=len(self.calls),
            task_id=task.id,
            outcome=self.outcome,
            started_at=moment,
            finished_at=moment,
            summary="esito",
            text="risultato",
        )


@pytest.fixture
def env(tmp_path: Path):
    db = Database(tmp_path / "agente.db")
    db.migrate()
    repos = repositories(db.connection)
    repos.users.upsert(User(telegram_id=USER, username="utente", state="accepted"))
    repos.users.upsert(User(telegram_id=REVOKED, username="revocato", state="revoked"))
    manager = TaskManager(
        repos.tasks,
        repos.subscriptions,
        repos.users,
        FakeRegistrar(),
        admin_id=ADMIN,
        min_interval_minutes=1,
    )

    def dispatcher(execution: FakeExecution | None = None) -> RunDispatcher:
        return RunDispatcher(
            tasks=manager,
            subscriptions=repos.subscriptions,
            users=repos.users,
            execution=execution or FakeExecution(),
            admin_id=ADMIN,
        )

    yield repos, manager, dispatcher
    db.close()


def _task(manager: TaskManager, name: str = "rassegna") -> Task:
    return manager.create(
        TaskDraft(
            name=name,
            instructions="riassumi i titoli",
            schedule=Schedule("orario", "08:00"),
        )
    )


def test_admin_may_run_any_task(env) -> None:
    _repos, manager, make = env
    task = _task(manager)
    execution = FakeExecution()
    dispatcher = make(execution)

    result = asyncio.run(dispatcher.run(Role.ADMIN, ADMIN, "rassegna"))

    assert result.outcome == "ok"
    assert execution.calls == [(task.id, "manual", ADMIN)]


def test_subscribed_user_runs_the_task(env) -> None:
    repos, manager, make = env
    task = _task(manager)
    repos.subscriptions.add(USER, task.id)
    execution = FakeExecution()

    result = asyncio.run(make(execution).run(Role.AUTHORIZED, USER, "rassegna"))

    assert result.task_id == task.id
    assert execution.calls == [(task.id, "manual", USER)]


def test_unsubscribed_user_is_refused(env) -> None:
    _repos, manager, make = env
    _task(manager, "log")
    execution = FakeExecution()

    with pytest.raises(RunRefused) as refused:
        asyncio.run(make(execution).run(Role.AUTHORIZED, USER, "log"))

    assert refused.value.reason == "forbidden"
    assert "Non sei iscritto" in str(refused.value)
    assert execution.calls == []


def test_unknown_role_is_refused(env) -> None:
    _repos, manager, make = env
    _task(manager)
    execution = FakeExecution()

    with pytest.raises(RunRefused) as refused:
        asyncio.run(make(execution).run(Role.UNKNOWN, 99, "rassegna"))

    assert refused.value.reason == "forbidden"
    assert execution.calls == []


def test_missing_name_is_refused(env) -> None:
    _repos, _manager, make = env

    with pytest.raises(RunRefused) as refused:
        asyncio.run(make().run(Role.ADMIN, ADMIN, "   "))

    assert refused.value.reason == "missing_name"


def test_unknown_task_lists_the_available_ones(env) -> None:
    repos, manager, make = env
    subscribed = _task(manager, "news")
    _task(manager, "log")
    repos.subscriptions.add(USER, subscribed.id)

    with pytest.raises(RunRefused) as refused:
        asyncio.run(make().run(Role.AUTHORIZED, USER, "bollettino"))

    message = str(refused.value)
    assert refused.value.reason == "not_found"
    assert "Compito non trovato: «bollettino»." in message
    assert "news" in message
    assert "log" not in message  # non iscritto: non compare nell'elenco


def test_admin_unknown_task_lists_every_task(env) -> None:
    _repos, manager, make = env
    _task(manager, "news")
    _task(manager, "log")

    with pytest.raises(RunRefused) as refused:
        asyncio.run(make().run(Role.ADMIN, ADMIN, "bollettino"))

    assert "news" in str(refused.value) and "log" in str(refused.value)


def test_admin_may_run_a_paused_task(env) -> None:
    _repos, manager, make = env
    task = _task(manager)
    manager.pause(task.id)
    execution = FakeExecution()

    result = asyncio.run(make(execution).run(Role.ADMIN, ADMIN, "rassegna"))

    assert result.outcome == "ok"
    assert execution.calls == [(task.id, "manual", ADMIN)]


def test_authorized_user_is_refused_on_a_paused_task(env) -> None:
    repos, manager, make = env
    task = _task(manager)
    repos.subscriptions.add(USER, task.id)
    manager.pause(task.id)
    execution = FakeExecution()

    with pytest.raises(RunRefused) as refused:
        asyncio.run(make(execution).run(Role.AUTHORIZED, USER, "rassegna"))

    assert refused.value.reason == "paused"
    assert "sospeso" in str(refused.value)
    assert execution.calls == []


def test_revoked_user_is_refused_at_launch(env) -> None:
    repos, manager, make = env
    task = _task(manager)
    repos.subscriptions.add(USER, task.id)
    repos.users.upsert(User(telegram_id=USER, username="utente", state="revoked"))
    execution = FakeExecution()

    with pytest.raises(RunRefused) as refused:
        asyncio.run(make(execution).run(Role.AUTHORIZED, USER, "rassegna"))

    assert refused.value.reason == "forbidden"
    assert execution.calls == []


def test_busy_task_is_refused(env) -> None:
    _repos, manager, make = env
    _task(manager)
    execution = FakeExecution(error=LockHeldError("in corso"))

    with pytest.raises(RunRefused) as refused:
        asyncio.run(make(execution).run(Role.ADMIN, ADMIN, "rassegna"))

    assert refused.value.reason == "busy"
    assert "già in esecuzione" in str(refused.value)


def test_lookup_ignores_case(env) -> None:
    _repos, manager, make = env
    _task(manager)
    execution = FakeExecution()

    asyncio.run(make(execution).run(Role.ADMIN, ADMIN, "RASSEGNA"))

    assert len(execution.calls) == 1
