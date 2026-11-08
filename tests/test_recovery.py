"""C-19: recupero delle occorrenze mancate, una sola volta (BR-5, AC-02)."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from agente.device_monitor import DeviceMonitor
from agente.errors import AgenteError, LockHeldError
from agente.execution import ExecutionResult
from agente.history import HistoryService
from agente.recovery import OFFLINE_SINCE, RecoveryHandler
from agente.schedule_registrar import ScheduleRegistrar
from agente.storage.db import Database
from agente.storage.repositories import Task, repositories

LOCAL = datetime.now().astimezone().tzinfo
NOW = datetime(2026, 10, 24, 9, 30, tzinfo=LOCAL)
MORNING = datetime(2026, 10, 24, 8, 0, tzinfo=LOCAL)
FUTURE = datetime(2026, 10, 25, 8, 0, tzinfo=LOCAL)


class FakeRegistrar:
    def __init__(self, future: datetime = FUTURE) -> None:
        self.markers: dict[int, datetime] = {}
        self.future = future
        self.updates = 0

    def next_run(self, task_id: int):
        return self.markers.get(task_id)

    def update(self, task) -> None:
        self.updates += 1
        self.markers[task.id] = self.future


class FakeEngine:
    def __init__(self, outcome: str = "ok", lock: bool = False) -> None:
        self.calls: list[tuple[int, str]] = []
        self.outcome = outcome
        self.lock = lock
        self.on_execute = None

    async def execute(self, task, trigger: str, requester=None) -> ExecutionResult:
        if self.lock:
            raise LockHeldError("esecuzione in corso")
        if self.on_execute is not None:
            self.on_execute()
        self.calls.append((task.id, trigger))
        moment = NOW.isoformat(timespec="seconds")
        return ExecutionResult(
            execution_id=len(self.calls),
            task_id=task.id,
            outcome=self.outcome,
            started_at=moment,
            finished_at=moment,
            summary="recuperato",
            text="recuperato",
        )


class FakeDevice:
    def __init__(self, online: bool = True) -> None:
        self.online = online
        self.contacts: list[object] = []

    def is_online(self) -> bool:
        return self.online

    def record_last_contact(self, settings, when=None) -> str:
        self.contacts.append(when)
        moment = (when or NOW).isoformat(timespec="seconds")
        settings.set("last_contact_at", moment)
        return moment


class FakeAlerts:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    async def alert(self, kind: str, detail: dict) -> bool:
        self.sent.append((kind, detail))
        return True


@pytest.fixture
def env(tmp_path: Path):
    db = Database(tmp_path / "agente.db")
    db.migrate()
    repos = repositories(db.connection)
    history = HistoryService(
        repos.executions,
        repos.conversations,
        retention_days=30,
        chat_memory_hours=24,
        clock=lambda: NOW,
    )
    registrar = FakeRegistrar()
    engine = FakeEngine()
    device = FakeDevice()
    alerts = FakeAlerts()

    def handler(online: bool | None = None) -> RecoveryHandler:
        if online is not None:
            device.online = online
        monitor = DeviceMonitor(
            device,  # type: ignore[arg-type]
            repos.settings,
            alerts,  # type: ignore[arg-type]
            battery_threshold_pct=15,
            offline_threshold_s=3600,
            clock=lambda: NOW,
        )
        return RecoveryHandler(
            tasks=repos.tasks,
            registrar=registrar,  # type: ignore[arg-type]
            engine=engine,  # type: ignore[arg-type]
            history=history,
            monitor=monitor,
            clock=lambda: NOW,
        )

    yield repos, history, registrar, engine, device, handler, alerts
    db.close()


def _task(repos, *, schedule_type: str = "orario", expr: str = "08:00") -> Task:
    return repos.tasks.create(
        Task(
            name="rassegna",
            instructions="notizie",
            schedule_type=schedule_type,
            schedule_expr=expr,
            created_by=1,
        )
    )


def test_only_last_occurrence_is_recovered(env) -> None:
    repos, _history, registrar, engine, _device, handler, _alerts = env
    task = _task(repos, schedule_type="intervallo", expr="30m")
    registrar.markers[task.id] = MORNING

    results = asyncio.run(handler().recover_missed())

    assert [call for call in engine.calls] == [(task.id, "recovery")]
    assert len(results) == 1 and results[0].outcome == "ok"
    stored = repos.executions.list(task_id=task.id)
    skipped = [execution for execution in stored if execution.outcome == "saltata"]
    assert len(skipped) == 3  # 08:00, 08:30, 09:00; 09:30 è recuperata
    assert registrar.markers[task.id] == FUTURE
    assert registrar.updates == 1


def test_recovery_is_idempotent(env) -> None:
    repos, _history, registrar, engine, _device, handler, _alerts = env
    task = _task(repos)
    registrar.markers[task.id] = MORNING

    first = asyncio.run(handler().recover_missed())
    second = asyncio.run(handler().recover_missed())

    assert len(first) == 1
    assert second == []
    assert len(engine.calls) == 1


def test_no_marker_means_nothing_to_recover(env) -> None:
    repos, _history, _registrar, engine, _device, handler, _alerts = env
    _task(repos)

    assert asyncio.run(handler().recover_missed()) == []
    assert engine.calls == []


def test_offline_postpones_recovery(env) -> None:
    repos, _history, registrar, engine, _device, handler, _alerts = env
    task = _task(repos)
    registrar.markers[task.id] = MORNING

    assert asyncio.run(handler(online=False).recover_missed()) == []
    assert engine.calls == []
    assert repos.executions.list() == []


def test_connectivity_uses_the_monitor(env) -> None:
    repos, _history, registrar, _engine, device, handler, alerts = env
    task = _task(repos)
    registrar.markers[task.id] = MORNING
    recovery = handler(online=False)

    asyncio.run(recovery.check_connectivity())
    assert repos.settings.get(OFFLINE_SINCE) is not None
    assert alerts.sent == []

    device.online = True
    results = asyncio.run(recovery.check_connectivity())

    assert len(results) == 1
    assert repos.settings.get(OFFLINE_SINCE) is None
    assert repos.settings.get("last_contact_at") is not None
    assert repos.settings.get("last_online_at") is not None
    assert alerts.sent == []


def test_long_offline_alerts_and_recovers(env) -> None:
    repos, _history, registrar, _engine, device, handler, alerts = env
    task = _task(repos)
    registrar.markers[task.id] = MORNING
    recovery = handler(online=False)
    repos.settings.set(OFFLINE_SINCE, "2026-10-24T07:00:00+02:00")
    device.online = True

    results = asyncio.run(recovery.check_connectivity())

    assert len(results) == 1
    assert alerts.sent[0][0] == "offline_resumed"
    assert alerts.sent[0][1]["offline_s"] > 3600


def test_invalid_marker_still_recovers(env) -> None:
    repos, _history, registrar, _engine, device, handler, alerts = env
    task = _task(repos)
    registrar.markers[task.id] = MORNING
    recovery = handler(online=False)
    repos.settings.set(OFFLINE_SINCE, "non-una-data")
    device.online = True

    results = asyncio.run(recovery.check_connectivity())

    assert len(results) == 1
    assert repos.settings.get(OFFLINE_SINCE) is None
    assert alerts.sent == []


def test_boot_does_not_alert(env) -> None:
    repos, _history, registrar, _engine, _device, handler, alerts = env
    task = _task(repos)
    registrar.markers[task.id] = MORNING
    repos.settings.set(OFFLINE_SINCE, "2026-10-24T07:00:00+02:00")

    asyncio.run(handler().recover_missed())

    assert alerts.sent == []


def test_paused_task_is_not_recovered(env) -> None:
    repos, _history, registrar, engine, _device, handler, _alerts = env
    task = _task(repos)
    repos.tasks.set_state(task.id, "paused")
    registrar.markers[task.id] = MORNING

    assert asyncio.run(handler().recover_missed()) == []
    assert engine.calls == []


def test_marker_key_is_owned_by_the_registrar() -> None:
    assert ScheduleRegistrar.setting_key(7) == "next_run:7"


def test_last_summary_counts_outcomes(env) -> None:
    repos, _history, registrar, engine, _device, handler, _alerts = env
    engine.outcome = "errore"
    task = _task(repos, schedule_type="intervallo", expr="30m")
    registrar.markers[task.id] = MORNING
    recovery = handler()

    results = asyncio.run(recovery.recover_missed())

    assert len(results) == 1
    stats = recovery.last_summary
    assert stats.recovered == 0
    assert stats.failed == 1
    assert stats.skipped == 3
    assert stats.deferred == 0
    assert stats.missed == 4


def test_last_summary_counts_deferred(env) -> None:
    repos, _history, registrar, engine, _device, handler, _alerts = env
    engine.lock = True
    task = _task(repos, schedule_type="intervallo", expr="30m")
    registrar.markers[task.id] = MORNING
    recovery = handler()

    assert asyncio.run(recovery.recover_missed()) == []

    stats = recovery.last_summary
    assert stats.recovered == 0
    assert stats.failed == 0
    assert stats.skipped == 3
    assert stats.deferred == 1
    assert stats.missed == 4


def test_last_summary_resets_on_postponed_recovery(env) -> None:
    repos, _history, registrar, _engine, device, handler, _alerts = env
    task = _task(repos, schedule_type="intervallo", expr="30m")
    registrar.markers[task.id] = MORNING
    recovery = handler()
    asyncio.run(recovery.recover_missed())
    assert recovery.last_summary.recovered == 1

    device.online = False
    assert asyncio.run(recovery.recover_missed()) == []
    assert recovery.last_summary.missed == 0
