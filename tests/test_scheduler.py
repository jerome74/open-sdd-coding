"""AC-05: i job attivi vengono ricaricati dallo stato persistito."""

from __future__ import annotations

import asyncio

import inspect

import pytest
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from agente import scheduler as scheduler_module
from agente.scheduler import BATTERY_JOB_ID, MAINTENANCE_JOB_ID, TaskScheduler, SchedulerError
from agente.storage.db import Database
from agente.storage.repositories import Task, repositories


def _scheduler(db_path: Path) -> TaskScheduler:
    inner = BackgroundScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{db_path}")},
        timezone=timezone.utc,
    )
    return TaskScheduler(db_path, scheduler=inner)


def _task(db_path: Path) -> Task:
    db = Database(db_path)
    db.migrate()
    task = repositories(db.connection).tasks.create(
        Task(
            name="rassegna",
            instructions="notizie",
            schedule_type="intervallo",
            schedule_expr="60",
            created_by=1,
        )
    )
    db.close()
    return task


def test_jobs_survive_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "agente.db"
    task = _task(db_path)

    first = _scheduler(db_path)
    first.start()
    first.schedule_task(task, IntervalTrigger(seconds=60))
    assert first.next_run(task.id) is not None
    first.shutdown()

    second = _scheduler(db_path)
    second.start()
    assert second.next_run(task.id) is not None
    assert [job.id for job in second.jobs()] == [TaskScheduler.job_id(task.id)]
    second.shutdown()


def test_unschedule_removes_job(tmp_path: Path) -> None:
    db_path = tmp_path / "agente.db"
    task = _task(db_path)
    scheduler = _scheduler(db_path)
    scheduler.start()
    scheduler.schedule_task(task, IntervalTrigger(seconds=30))
    scheduler.unschedule_task(task.id)
    assert scheduler.next_run(task.id) is None
    scheduler.unschedule_task(task.id)  # idempotente
    scheduler.shutdown()


def test_only_one_instance_per_task(tmp_path: Path) -> None:
    db_path = tmp_path / "agente.db"
    task = _task(db_path)
    scheduler = _scheduler(db_path)
    scheduler.start()
    scheduler.schedule_task(task, IntervalTrigger(seconds=30))
    scheduler.schedule_task(task, IntervalTrigger(seconds=45))
    assert len(scheduler.jobs()) == 1
    scheduler.shutdown()


def test_production_scheduler_is_asyncio(tmp_path: Path) -> None:
    scheduler = TaskScheduler(tmp_path / "agente.db")
    assert isinstance(scheduler._scheduler, AsyncIOScheduler)


def test_maintenance_job_calls_history_and_persists(tmp_path: Path) -> None:
    db_path = tmp_path / "agente.db"
    calls: list[int] = []
    first = _scheduler(db_path)
    first.start()
    first.schedule_maintenance(lambda: calls.append(1))
    assert MAINTENANCE_JOB_ID in [job.id for job in first.jobs()]

    asyncio.run(scheduler_module._run_maintenance_job())
    assert calls == [1]
    first.shutdown()

    second = _scheduler(db_path)
    second.start()
    assert [job.id for job in second.jobs()] == [MAINTENANCE_JOB_ID]
    second.shutdown()


def test_dispatcher_entrypoint_is_a_coroutine_function() -> None:
    assert inspect.iscoroutinefunction(scheduler_module._run_scheduled_job)
    assert inspect.iscoroutinefunction(scheduler_module._run_connectivity_job)


def test_dispatcher_entrypoint_awaits_the_callback() -> None:
    import asyncio

    calls: list[int] = []

    async def dispatcher(task_id: int) -> None:
        calls.append(task_id)

    scheduler_module._DISPATCHER = dispatcher
    try:
        asyncio.run(scheduler_module._run_scheduled_job(7))
    finally:
        scheduler_module._DISPATCHER = None

    assert calls == [7]


def test_start_paused_loads_jobs_without_running_them(tmp_path: Path) -> None:
    db_path = tmp_path / "agente.db"
    task = _task(db_path)

    first = _scheduler(db_path)
    first.start()
    first.schedule_task(task, IntervalTrigger(minutes=5))
    first.shutdown()

    second = _scheduler(db_path)
    second.start(paused=True)
    try:
        assert second.next_run(task.id) is not None
        second.resume()
    finally:
        second.shutdown()


def test_async_scheduler_fires_the_job_into_the_dispatcher(tmp_path: Path) -> None:
    import asyncio
    from datetime import datetime, timedelta

    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.date import DateTrigger

    async def scenario() -> list[int]:
        inner = AsyncIOScheduler(timezone=timezone.utc)
        scheduler = TaskScheduler(tmp_path / "async.db", scheduler=inner)
        calls: list[int] = []

        async def dispatcher(task_id: int) -> None:
            calls.append(task_id)

        scheduler.set_dispatcher(dispatcher)
        scheduler.start()
        task = Task(
            name="async",
            instructions="x",
            schedule_type="orario",
            schedule_expr="08:00",
            created_by=1,
            id=1,
        )
        scheduler.schedule_task(
            task, DateTrigger(run_date=datetime.now(timezone.utc) + timedelta(seconds=0.1))
        )
        await asyncio.sleep(1.2)
        scheduler.shutdown()
        return calls

    try:
        assert asyncio.run(scenario()) == [1]
    finally:
        scheduler_module._DISPATCHER = None


def test_maintenance_job_runs_in_the_event_loop(tmp_path: Path) -> None:
    """Spec 05 D8: il purge gira nell'event loop, dove vive la connessione SQLite."""
    assert inspect.iscoroutinefunction(scheduler_module._run_maintenance_job)
    calls: list[str] = []

    async def callback() -> None:
        calls.append("async")

    scheduler = _scheduler(tmp_path / "agente.db")
    scheduler.start()
    scheduler.schedule_maintenance(callback)
    try:
        asyncio.run(scheduler_module._run_maintenance_job())
        assert calls == ["async"]
    finally:
        scheduler.shutdown()


def test_battery_job_is_registered(tmp_path: Path) -> None:
    calls: list[str] = []

    async def callback() -> None:
        calls.append("battery")

    scheduler = _scheduler(tmp_path / "battery.db")
    scheduler.start()
    try:
        assert scheduler.schedule_battery(callback, interval_s=120) == BATTERY_JOB_ID
        job = scheduler._scheduler.get_job(BATTERY_JOB_ID)
        assert job is not None
        assert int(job.trigger.interval.total_seconds()) == 120
        asyncio.run(scheduler_module._run_battery_job())
        assert calls == ["battery"]
    finally:
        scheduler.shutdown()


def test_battery_job_error_is_isolated(tmp_path: Path) -> None:
    async def callback() -> None:
        raise RuntimeError("batteria")

    scheduler = _scheduler(tmp_path / "battery-error.db")
    scheduler.start()
    try:
        scheduler.schedule_battery(callback)
        assert asyncio.run(scheduler_module._run_battery_job()) is None
    finally:
        scheduler.shutdown()


def test_battery_interval_must_be_positive(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path / "battery-negative.db")
    scheduler.start()

    try:
        with pytest.raises(SchedulerError):
            scheduler.schedule_battery(lambda: None, interval_s=0)
    finally:
        scheduler.shutdown()


def test_liveness_job_is_registered(tmp_path: Path) -> None:
    calls: list[str] = []

    async def callback() -> None:
        calls.append("liveness")

    scheduler = _scheduler(tmp_path / "liveness.db")
    scheduler.start()
    try:
        assert scheduler.schedule_liveness(callback, at="07:30") == "liveness:send"
        job = scheduler._scheduler.get_job("liveness:send")
        assert job is not None
        assert "hour='7'" in str(job.trigger)
        assert "minute='30'" in str(job.trigger)
        asyncio.run(scheduler_module._run_liveness_job())
        assert calls == ["liveness"]
    finally:
        scheduler.shutdown()


def test_liveness_job_is_replaced_with_a_fresh_trigger(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path / "liveness-replace.db")
    scheduler.start()
    try:
        scheduler.schedule_liveness(lambda: None, at="09:00")
        scheduler.schedule_liveness(lambda: None, at="10:15")
        jobs = [job for job in scheduler._scheduler.get_jobs() if job.id == "liveness:send"]
        assert len(jobs) == 1
        assert "hour='10'" in str(jobs[0].trigger)
        assert "minute='15'" in str(jobs[0].trigger)
    finally:
        scheduler.shutdown()


def test_liveness_job_has_no_misfire_grace(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path / "liveness-grace.db")
    scheduler.start()
    try:
        scheduler.schedule_liveness(lambda: None)
        job = scheduler._scheduler.get_job("liveness:send")
        assert job.misfire_grace_time is None
    finally:
        scheduler.shutdown()


def test_liveness_job_uses_the_scheduler_timezone(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path / "liveness-tz.db")
    scheduler.start()
    try:
        scheduler.schedule_liveness(lambda: None)
        job = scheduler._scheduler.get_job("liveness:send")
        assert job.trigger.timezone == timezone.utc
    finally:
        scheduler.shutdown()


def test_liveness_job_error_is_isolated(tmp_path: Path) -> None:
    async def callback() -> None:
        raise RuntimeError("liveness")

    scheduler = _scheduler(tmp_path / "liveness-error.db")
    scheduler.start()
    try:
        scheduler.schedule_liveness(callback)
        assert asyncio.run(scheduler_module._run_liveness_job()) is None
    finally:
        scheduler.shutdown()


def test_liveness_time_must_be_valid(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path / "liveness-invalid.db")
    scheduler.start()
    try:
        for value in ("24:00", "08:60", "boh", "8"):
            with pytest.raises(SchedulerError):
                scheduler.schedule_liveness(lambda: None, at=value)
    finally:
        scheduler.shutdown()
