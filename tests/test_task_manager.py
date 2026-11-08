"""C-15: CRUD, validazioni e limite BR-16 dei compiti."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from agente.role_guard import Role
from agente.schedule_interpreter import Schedule
from agente.storage.db import Database
from agente.storage.repositories import User, repositories
from agente.task_manager import (
    MAX_ACTIVE_TASKS,
    TaskDraft,
    TaskManager,
    TaskValidationError,
)

ADMIN = 1

ORARIO = Schedule("orario", "08:00")
INTERVALLO = Schedule("intervallo", "2h")


class FakeRegistrar:
    def __init__(self) -> None:
        self.scheduled: list[int] = []
        self.unscheduled: list[int] = []
        self.registered: list[int] = []
        self.updated: list[int] = []

    def register(self, task):
        self.registered.append(task.id)
        self.scheduled.append(task.id)
        return f"task:{task.id}"

    def update(self, task):
        self.updated.append(task.id)
        self.scheduled.append(task.id)
        return f"task:{task.id}"

    def unregister(self, task_id: int) -> None:
        self.unscheduled.append(task_id)

    def refresh(self, task_id: int):
        return None

    def next_run(self, task_id: int):
        return None


@pytest.fixture
def manager(tmp_path: Path):
    db = Database(tmp_path / "agente.db")
    db.migrate()
    repos = repositories(db.connection)
    repos.users.upsert(User(telegram_id=2, username="utente", state="accepted"))
    registrar = FakeRegistrar()
    engine = TaskManager(
        repos.tasks,
        repos.subscriptions,
        repos.users,
        registrar,
        admin_id=ADMIN,
        min_interval_minutes=1,
        clock=lambda: datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc),
    )
    yield engine, repos, registrar
    db.close()


def draft(name: str = "rassegna", **overrides) -> TaskDraft:
    values = {
        "name": name,
        "instructions": "riassumi i log",
        "schedule": ORARIO,
        "recipients": (),
        "log_allowlist": (),
    }
    values.update(overrides)
    return TaskDraft(**values)


def test_create_persists_task_and_schedules_job(manager) -> None:
    engine, repos, scheduler = manager
    task = engine.create(draft())
    assert task.id is not None
    assert task.state == "active"
    assert task.schedule_type == "orario"
    assert task.instructions == "riassumi i log"
    assert task.created_by == ADMIN
    assert repos.tasks.get(task.id).name == "rassegna"
    assert scheduler.scheduled == [task.id]
    assert repos.subscriptions.users_for_task(task.id) == []
    assert engine.list(Role.ADMIN, ADMIN)[0].recipients == (ADMIN,)


def test_name_is_unique_case_insensitive(manager) -> None:
    engine, _, _ = manager
    engine.create(draft("Caffè"))
    with pytest.raises(TaskValidationError):
        engine.create(draft("caffè"))
    assert engine.find("CAFFÈ") is not None


def test_missing_fields_are_rejected(manager) -> None:
    engine, _, _ = manager
    with pytest.raises(TaskValidationError):
        engine.create(draft("  "))
    with pytest.raises(TaskValidationError):
        engine.create(draft("x", instructions=" "))


def test_minimum_interval_is_enforced(manager) -> None:
    engine, _, _ = manager
    with pytest.raises(TaskValidationError):
        engine.create(draft("x", schedule=Schedule("intervallo", "0m")))
    task = engine.create(draft("y", schedule=Schedule("intervallo", "1m")))
    assert task.schedule_expr == "1m"


def test_active_task_limit_is_enforced(manager) -> None:
    engine, _, _ = manager
    for index in range(MAX_ACTIVE_TASKS):
        engine.create(draft(f"compito-{index}"))
    with pytest.raises(TaskValidationError):
        engine.create(draft("uno-di-troppo"))


def test_recipients_must_be_authorized_and_admin_is_always_included(manager) -> None:
    engine, repos, _ = manager
    task = engine.create(draft(recipients=(2,)))
    assert set(repos.subscriptions.users_for_task(task.id)) == {2}
    assert engine.list(Role.ADMIN, ADMIN)[0].recipients == (ADMIN, 2)
    with pytest.raises(TaskValidationError):
        engine.create(draft("altro", recipients=(999,)))

    repos.users.upsert(User(telegram_id=3, username="pending", state="pending"))
    with pytest.raises(TaskValidationError):
        engine.create(draft("terzo", recipients=(3,)))


def test_pause_resume_delete_update_jobs(manager) -> None:
    engine, repos, scheduler = manager
    task = engine.create(draft())

    engine.pause(task.id)
    assert repos.tasks.get(task.id).state == "paused"
    assert scheduler.unscheduled == [task.id]

    engine.resume(task.id)
    assert repos.tasks.get(task.id).state == "active"
    assert scheduler.scheduled == [task.id, task.id]

    engine.delete(task.id)
    assert repos.tasks.get(task.id) is None
    assert scheduler.unscheduled == [task.id, task.id]


def test_resume_honours_active_limit(manager) -> None:
    engine, _, _ = manager
    for index in range(MAX_ACTIVE_TASKS):
        engine.create(draft(f"c-{index}"))
    first = engine.find("c-0")
    assert first is not None
    engine.pause(first.id)
    engine.create(draft("ultimo"))
    with pytest.raises(TaskValidationError):
        engine.resume(first.id)


def test_rename_and_duplicate_guard(manager) -> None:
    engine, _, _ = manager
    first = engine.create(draft("primo"))
    engine.create(draft("secondo"))
    renamed = engine.rename(first.id, "Primo Nuovo")
    assert renamed.name == "Primo Nuovo"
    with pytest.raises(TaskValidationError):
        engine.rename(first.id, "SECONDO")


def test_update_changes_schedule_and_reschedules(manager) -> None:
    engine, repos, scheduler = manager
    task = engine.create(draft())
    engine.update(task.id, _delta(schedule=Schedule("intervallo", "3h")))
    updated = repos.tasks.get(task.id)
    assert (updated.schedule_type, updated.schedule_expr) == ("intervallo", "3h")
    assert scheduler.scheduled[-1] == task.id


def test_list_by_role(manager) -> None:
    engine, repos, _ = manager
    first = engine.create(draft("alfa"))
    engine.create(draft("beta"))
    repos.subscriptions.add(2, first.id)
    assert len(engine.list(Role.ADMIN, ADMIN)) == 2
    views = engine.list(Role.AUTHORIZED, 2)
    assert [view.task.name for view in views] == ["alfa"]
    assert views[0].recipients == (ADMIN, 2)
    assert engine.list(Role.UNKNOWN, 2) == []


def _delta(**kwargs):
    from agente.task_manager import TaskDelta

    return TaskDelta(**kwargs)
