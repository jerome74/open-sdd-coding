"""C-18: registrazione job, trigger e marcatore `next_run` (spec 03)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from tzlocal import get_localzone

from agente.schedule_registrar import ScheduleRegistrar
from agente.storage.db import Database
from agente.storage.repositories import Task, repositories

NOW = datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc)
NEXT = datetime(2026, 10, 25, 8, 0, tzinfo=timezone.utc)


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: dict[int, object] = {}
        self.next_runs: dict[int, datetime] = {}
        self.unscheduled: list[int] = []
        self.fail = False

    def schedule_task(self, task, trigger):
        if self.fail:
            raise RuntimeError("scheduler guasto")
        self.jobs[task.id] = trigger
        self.next_runs.setdefault(task.id, NEXT)
        return f"task:{task.id}"

    def unschedule_task(self, task_id: int) -> None:
        self.unscheduled.append(task_id)
        self.jobs.pop(task_id, None)
        self.next_runs.pop(task_id, None)

    def next_run(self, task_id: int):
        return self.next_runs.get(task_id)


@pytest.fixture
def env(tmp_path: Path):
    db = Database(tmp_path / "agente.db")
    db.migrate()
    repos = repositories(db.connection)
    scheduler = FakeScheduler()
    registrar = ScheduleRegistrar(repos.settings, scheduler, clock=lambda: NOW)
    task = repos.tasks.create(
        Task(
            name="rassegna",
            instructions="notizie",
            schedule_type="orario",
            schedule_expr="08:00",
            created_by=1,
        )
    )
    yield repos, scheduler, registrar, task
    db.close()


def test_register_creates_job_and_persists_next_run(env) -> None:
    repos, scheduler, registrar, task = env

    job_id = registrar.register(task)

    assert job_id == f"task:{task.id}"
    assert isinstance(scheduler.jobs[task.id], CronTrigger)
    assert "hour='8'" in str(scheduler.jobs[task.id])
    assert "minute='0'" in str(scheduler.jobs[task.id])
    stored = repos.settings.get(registrar.setting_key(task.id))
    assert stored == NEXT.isoformat(timespec="seconds")
    assert registrar.next_run(task.id) == NEXT


def test_interval_is_anchored_at_registration(env) -> None:
    _repos, scheduler, registrar, task = env
    task.schedule_type = "intervallo"
    task.schedule_expr = "2h"

    registrar.register(task)

    trigger = scheduler.jobs[task.id]
    assert isinstance(trigger, IntervalTrigger)
    assert trigger.start_date == NOW


def test_update_replaces_job_and_marker(env) -> None:
    _repos, scheduler, registrar, task = env
    registrar.register(task)
    task.schedule_type = "intervallo"
    task.schedule_expr = "30m"

    registrar.update(task)

    assert isinstance(scheduler.jobs[task.id], IntervalTrigger)
    assert scheduler.unscheduled == []
    assert registrar.next_run(task.id) == NEXT


def test_unregister_removes_job_and_marker(env) -> None:
    repos, scheduler, registrar, task = env
    registrar.register(task)

    registrar.unregister(task.id)

    assert scheduler.unscheduled == [task.id]
    assert task.id not in scheduler.jobs
    assert repos.settings.get(registrar.setting_key(task.id)) is None


def test_refresh_without_job_clears_marker(env) -> None:
    repos, scheduler, registrar, task = env
    registrar.register(task)
    scheduler.next_runs.pop(task.id)

    assert registrar.refresh(task.id) is None
    assert repos.settings.get(registrar.setting_key(task.id)) is None


def test_sync_seeds_markers_without_rescheduling(env) -> None:
    _repos, scheduler, registrar, task = env
    scheduler.next_runs[task.id] = NEXT

    registrar.sync([task])

    assert scheduler.jobs == {}
    assert registrar.next_run(task.id) == NEXT


def test_failure_leaves_no_partial_state(env) -> None:
    repos, scheduler, registrar, task = env
    scheduler.fail = True

    with pytest.raises(RuntimeError):
        registrar.register(task)

    assert task.id in scheduler.unscheduled
    assert repos.settings.get(registrar.setting_key(task.id)) is None


def test_unreadable_marker_is_ignored(env) -> None:
    repos, _scheduler, registrar, task = env
    repos.settings.set(registrar.setting_key(task.id), "non-una-data")

    assert registrar.next_run(task.id) is None


def test_trigger_uses_the_phone_timezone(env) -> None:
    _repos, scheduler, registrar, task = env

    registrar.register(task)

    trigger = scheduler.jobs[task.id]
    # Nessuna timezone forzata: APScheduler usa il fuso del telefono (BR-14).
    assert trigger.timezone == get_localzone()
