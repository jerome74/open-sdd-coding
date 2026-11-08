"""C-39: sequenza di avvio, periodo di assenza e segnale mancato (spec 11)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest

from agente.boot import LAST_START_AT, BootRecovery
from agente.device_monitor import LAST_ONLINE_AT, OFFLINE_SINCE
from agente.errors import AgenteError
from agente.execution import ExecutionResult
from agente.history import HistoryService
from agente.liveness import LIVENESS_MARKER
from agente.recovery import RecoveryHandler
from agente.storage.db import Database
from agente.storage.repositories import Task, repositories

NOW = datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc)
FUTURE = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)


class FakeScheduler:
    def __init__(self) -> None:
        self.started = False
        self.paused = False
        self.resumed = False

    def start(self, *, paused: bool = False) -> None:
        self.started = True
        self.paused = paused

    def resume(self) -> None:
        self.resumed = True


class FakeRegistrar:
    def __init__(self, settings) -> None:
        self._settings = settings
        self.synced: list[int] = []
        self.updates = 0

    @staticmethod
    def _key(task_id: int) -> str:
        return f"next_run:{task_id}"

    def next_run(self, task_id: int):
        raw = self._settings.get(self._key(task_id))
        return None if raw is None else datetime.fromisoformat(raw)

    def update(self, task) -> None:
        self.updates += 1
        self._settings.set(
            self._key(task.id), FUTURE.isoformat(timespec="seconds")
        )

    def sync(self, tasks) -> None:
        self.synced = [task.id for task in tasks]


class FakeMonitor:
    def __init__(self, online: bool = True) -> None:
        self.online = online

    async def is_online(self) -> bool:
        return self.online


class FakeEngine:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0
        self.on_execute = None

    async def execute(self, task, trigger: str, requester=None) -> ExecutionResult:
        if self.on_execute is not None:
            self.on_execute()
        if self.error is not None:
            raise self.error
        self.calls += 1
        moment = NOW.isoformat(timespec="seconds")
        return ExecutionResult(
            execution_id=self.calls,
            task_id=task.id,
            outcome="ok",
            started_at=moment,
            finished_at=moment,
            summary="ok",
            text="ok",
        )


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "boot.db")
    db.migrate()
    repos = repositories(db.connection)
    history = HistoryService(
        repos.executions,
        repos.conversations,
        retention_days=30,
        chat_memory_hours=24,
        clock=lambda: NOW,
    )
    scheduler = FakeScheduler()
    registrar = FakeRegistrar(repos.settings)
    engine = FakeEngine()
    monitor = FakeMonitor()
    recovery = RecoveryHandler(
        tasks=repos.tasks,
        registrar=registrar,  # type: ignore[arg-type]
        engine=engine,  # type: ignore[arg-type]
        history=history,
        monitor=monitor,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )

    def boot() -> BootRecovery:
        return BootRecovery(
            scheduler=scheduler,  # type: ignore[arg-type]
            registrar=registrar,  # type: ignore[arg-type]
            tasks=repos.tasks,
            recovery=recovery,
            settings=repos.settings,
            liveness_at="08:00",
            clock=lambda: NOW,
        )

    yield repos, scheduler, registrar, engine, monitor, recovery, boot
    db.close()


def _task(repos, *, expr: str = "30m") -> Task:
    return repos.tasks.create(
        Task(
            name="rassegna",
            instructions="notizie",
            schedule_type="intervallo",
            schedule_expr=expr,
            created_by=1,
        )
    )


def test_first_start_has_no_period_and_no_message(env) -> None:
    repos, scheduler, _registrar, _engine, _monitor, _recovery, boot = env

    summary = asyncio.run(boot().on_start())

    assert summary.offline_period is None
    assert summary.liveness_missed is False
    assert summary.missed_count == 0
    assert repos.settings.get(LAST_START_AT) == NOW.isoformat(timespec="seconds")
    assert scheduler.started and scheduler.paused is True
    assert scheduler.resumed is True


def test_absence_period_uses_last_online_at(env) -> None:
    repos, _scheduler, _registrar, _engine, _monitor, _recovery, boot = env
    repos.settings.set(
        LAST_START_AT, (NOW - timedelta(days=2)).isoformat(timespec="seconds")
    )
    repos.settings.set(
        LAST_ONLINE_AT, (NOW - timedelta(hours=2)).isoformat(timespec="seconds")
    )

    summary = asyncio.run(boot().on_start())

    assert summary.offline_period is not None
    assert summary.offline_period.since == NOW - timedelta(hours=2)
    assert summary.offline_period.until == NOW
    assert summary.offline_period.seconds == 7200


def test_absence_period_falls_back_to_last_start(env) -> None:
    repos, _scheduler, _registrar, _engine, _monitor, _recovery, boot = env
    repos.settings.set(
        LAST_START_AT, (NOW - timedelta(hours=3)).isoformat(timespec="seconds")
    )

    summary = asyncio.run(boot().on_start())

    assert summary.offline_period is not None
    assert summary.offline_period.seconds == 10800


def test_period_is_captured_before_recovery(env) -> None:
    repos, _scheduler, _registrar, engine, _monitor, _recovery, boot = env
    repos.settings.set(
        LAST_START_AT, (NOW - timedelta(days=2)).isoformat(timespec="seconds")
    )
    repos.settings.set(
        LAST_ONLINE_AT, (NOW - timedelta(hours=2)).isoformat(timespec="seconds")
    )

    def move_marker() -> None:
        repos.settings.set(
            LAST_ONLINE_AT, NOW.isoformat(timespec="seconds")
        )

    engine.on_execute = move_marker
    _task(repos)
    repos.settings.set("next_run:1", (NOW - timedelta(minutes=30)).isoformat())

    summary = asyncio.run(boot().on_start())

    assert summary.offline_period is not None
    assert summary.offline_period.seconds == 7200


def test_last_start_is_written_after_recovery(env) -> None:
    repos, _scheduler, _registrar, engine, _monitor, _recovery, boot = env
    previous = (NOW - timedelta(days=1)).isoformat(timespec="seconds")
    repos.settings.set(LAST_START_AT, previous)
    task = _task(repos)
    repos.settings.set(
        f"next_run:{task.id}", (NOW - timedelta(hours=1)).isoformat()
    )
    seen: list[str | None] = []

    def read_marker() -> None:
        seen.append(repos.settings.get(LAST_START_AT))

    engine.on_execute = read_marker
    asyncio.run(boot().on_start())

    assert seen == [previous]


def test_recovery_error_fails_start(env) -> None:
    repos, _scheduler, _registrar, engine, _monitor, _recovery, boot = env
    previous = (NOW - timedelta(days=1)).isoformat(timespec="seconds")
    repos.settings.set(LAST_START_AT, previous)
    task = _task(repos)
    repos.settings.set(
        f"next_run:{task.id}", (NOW - timedelta(hours=1)).isoformat()
    )
    engine.error = AgenteError("recupero")

    with pytest.raises(AgenteError):
        asyncio.run(boot().on_start())

    assert repos.settings.get(LAST_START_AT) == previous


def test_liveness_missed_before_and_after_eight(env) -> None:
    repos, _scheduler, _registrar, _engine, _monitor, _recovery, boot = env
    repos.settings.set(
        LAST_START_AT, (NOW - timedelta(days=1)).isoformat(timespec="seconds")
    )

    summary = asyncio.run(boot().on_start())

    assert summary.liveness_missed is True


def test_liveness_not_missed_when_already_sent(env) -> None:
    repos, _scheduler, _registrar, _engine, _monitor, _recovery, boot = env
    repos.settings.set(
        LAST_START_AT, (NOW - timedelta(days=1)).isoformat(timespec="seconds")
    )
    repos.settings.set(
        LIVENESS_MARKER, NOW.replace(hour=8, minute=30).isoformat(timespec="seconds")
    )

    summary = asyncio.run(boot().on_start())

    assert summary.liveness_missed is False


def test_liveness_before_previous_start_is_not_missed(env) -> None:
    repos, _scheduler, _registrar, _engine, _monitor, _recovery, boot = env
    repos.settings.set(
        LAST_START_AT, NOW.replace(hour=8, minute=30).isoformat(timespec="seconds")
    )

    summary = asyncio.run(boot().on_start())

    assert summary.liveness_missed is False


def test_invalid_last_online_falls_back_to_start(env) -> None:
    repos, _scheduler, _registrar, _engine, _monitor, _recovery, boot = env
    repos.settings.set(
        LAST_START_AT, (NOW - timedelta(hours=3)).isoformat(timespec="seconds")
    )
    repos.settings.set(LAST_ONLINE_AT, "non-una-data")

    summary = asyncio.run(boot().on_start())

    assert summary.offline_period is not None
    assert summary.offline_period.seconds == 10800


def test_invalid_markers_are_ignored(env) -> None:
    repos, _scheduler, _registrar, _engine, _monitor, _recovery, boot = env
    repos.settings.set(LAST_START_AT, "non-una-data")
    repos.settings.set(
        LAST_ONLINE_AT, (NOW - timedelta(hours=2)).isoformat(timespec="seconds")
    )

    summary = asyncio.run(boot().on_start())

    assert summary.offline_period is None
    assert summary.liveness_missed is False


def test_naive_marker_is_read_as_utc(env) -> None:
    repos, _scheduler, _registrar, _engine, _monitor, _recovery, boot = env
    repos.settings.set(LAST_START_AT, "2026-11-03T09:00:00")
    repos.settings.set(LAST_ONLINE_AT, "2026-11-04T07:00:00")

    summary = asyncio.run(boot().on_start())

    assert summary.offline_period is not None
    assert summary.offline_period.seconds == 7200


def test_boot_ignores_offline_since(env) -> None:
    repos, _scheduler, _registrar, _engine, _monitor, _recovery, boot = env
    repos.settings.set(
        LAST_START_AT, (NOW - timedelta(hours=1)).isoformat(timespec="seconds")
    )
    repos.settings.set(
        OFFLINE_SINCE, (NOW - timedelta(hours=5)).isoformat(timespec="seconds")
    )

    summary = asyncio.run(boot().on_start())

    assert summary.offline_period is not None
    assert summary.offline_period.seconds == 3600


def test_start_logs_period_and_recovery(env, caplog) -> None:
    repos, _scheduler, _registrar, _engine, _monitor, _recovery, boot = env
    repos.settings.set(
        LAST_START_AT, (NOW - timedelta(hours=2)).isoformat(timespec="seconds")
    )

    with caplog.at_level(logging.INFO, logger="agente.boot"):
        asyncio.run(boot().on_start())

    record = [r for r in caplog.records if r.message == "avvio completato"][0]
    assert record.offline_s == 7200
    assert record.recovered == 0
    assert record.liveness_missed is True
