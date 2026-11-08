"""AC-01…AC-04 di spec 11, con dipendenze esterne finte."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from agente.boot import LAST_START_AT, BootRecovery
from agente.device_monitor import LAST_ONLINE_AT
from agente.errors import TelegramError
from agente.execution import ExecutionResult
from agente.history import HistoryService
from agente.liveness import LIVENESS_MARKER, LivenessScheduler
from agente.recovery import RecoveryHandler
from agente.restart import RestartNotifier
from agente.storage.db import Database
from agente.storage.repositories import Task, repositories

NOW = datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc)
FUTURE = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)


class FakeNotifications:
    def __init__(self, *, fail: bool = False) -> None:
        self.texts: list[str] = []
        self.fail = fail
        self.calls = 0

    async def alert_admin(self, text: str) -> None:
        self.calls += 1
        if self.fail:
            raise TelegramError("telegram non raggiungibile")
        self.texts.append(text)


class FakeScheduler:
    def start(self, *, paused: bool = False) -> None:
        return None

    def resume(self) -> None:
        return None


class FakeRegistrar:
    def __init__(self, settings) -> None:
        self._settings = settings

    @staticmethod
    def _key(task_id: int) -> str:
        return f"next_run:{task_id}"

    def next_run(self, task_id: int):
        raw = self._settings.get(self._key(task_id))
        return None if raw is None else datetime.fromisoformat(raw)

    def update(self, task) -> None:
        self._settings.set(
            self._key(task.id), FUTURE.isoformat(timespec="seconds")
        )

    def sync(self, tasks) -> None:
        return None


class FakeMonitor:
    async def is_online(self) -> bool:
        return True


class FakeEngine:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, task, trigger: str, requester=None) -> ExecutionResult:
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
    db = Database(tmp_path / "restart_ac.db")
    db.migrate()
    repos = repositories(db.connection)
    history = HistoryService(
        repos.executions,
        repos.conversations,
        retention_days=30,
        chat_memory_hours=24,
        clock=lambda: NOW,
    )
    notifications = FakeNotifications()
    engine = FakeEngine()
    registrar = FakeRegistrar(repos.settings)
    recovery = RecoveryHandler(
        tasks=repos.tasks,
        registrar=registrar,  # type: ignore[arg-type]
        engine=engine,  # type: ignore[arg-type]
        history=history,
        monitor=FakeMonitor(),  # type: ignore[arg-type]
        clock=lambda: NOW,
    )
    boot = BootRecovery(
        scheduler=FakeScheduler(),  # type: ignore[arg-type]
        registrar=registrar,  # type: ignore[arg-type]
        tasks=repos.tasks,
        recovery=recovery,
        settings=repos.settings,
        liveness_at="08:00",
        clock=lambda: NOW,
    )
    notifier = RestartNotifier(
        notifications, at="08:00", clock=lambda: NOW  # type: ignore[arg-type]
    )
    liveness = LivenessScheduler(
        notifications,  # type: ignore[arg-type]
        repos.settings,
        at="08:00",
        clock=lambda: NOW,
    )

    async def run_boot() -> None:
        summary = await boot.on_start()
        await notifier.notify_restart(
            summary, summary.offline_period, summary.liveness_missed
        )

    yield repos, notifications, engine, run_boot, liveness
    db.close()


def _task(repos, name: str = "rassegna") -> Task:
    return repos.tasks.create(
        Task(
            name=name,
            instructions="notizie",
            schedule_type="intervallo",
            schedule_expr="30m",
            created_by=1,
        )
    )


def test_ac01_restart_sends_message(env) -> None:
    repos, notifications, engine, run_boot, _liveness = env
    task = _task(repos)
    repos.settings.set(
        LAST_START_AT, (NOW - timedelta(days=1)).isoformat(timespec="seconds")
    )
    repos.settings.set(
        LAST_ONLINE_AT, (NOW - timedelta(hours=2)).isoformat(timespec="seconds")
    )
    repos.settings.set(
        f"next_run:{task.id}", (NOW - timedelta(hours=1)).isoformat()
    )

    asyncio.run(run_boot())

    assert engine.calls == 1
    text = notifications.texts[0]
    assert "Sono di nuovo attivo" in text
    assert "2 h" in text
    assert "recuperato 1 compito" in text


def test_ac02_liveness_at_eight(env) -> None:
    repos, notifications, _engine, _run_boot, liveness = env

    assert asyncio.run(liveness.send_liveness()) is True

    assert notifications.texts == ["✅ Segnale di vita: tutto ok (08:00)."]
    assert repos.settings.get(LIVENESS_MARKER) == NOW.isoformat(
        timespec="seconds"
    )


def test_ac03_missed_liveness_is_reported(env) -> None:
    repos, notifications, _engine, run_boot, _liveness = env
    repos.settings.set(
        LAST_START_AT, (NOW - timedelta(days=2)).isoformat(timespec="seconds")
    )
    repos.settings.set(
        LAST_ONLINE_AT, "2026-11-03T06:00:00+00:00"
    )
    repos.settings.set(
        LIVENESS_MARKER, "2026-11-03T07:00:00+00:00"
    )

    asyncio.run(run_boot())

    text = notifications.texts[0]
    assert "Segnale delle 08:00 non inviato" in text
    assert "— offline dalle" in text.splitlines()[1]


def test_ac04_repeated_boots_are_idempotent(env) -> None:
    repos, notifications, engine, _run_boot, _liveness = env
    task = _task(repos)
    repos.settings.set(
        LAST_START_AT, (NOW - timedelta(days=1)).isoformat(timespec="seconds")
    )
    repos.settings.set(
        LAST_ONLINE_AT, (NOW - timedelta(hours=1)).isoformat(timespec="seconds")
    )
    repos.settings.set(
        f"next_run:{task.id}", (NOW - timedelta(minutes=30)).isoformat()
    )

    def make_boot() -> BootRecovery:
        registrar = FakeRegistrar(repos.settings)
        return BootRecovery(
            scheduler=FakeScheduler(),  # type: ignore[arg-type]
            registrar=registrar,  # type: ignore[arg-type]
            tasks=repos.tasks,
            recovery=RecoveryHandler(
                tasks=repos.tasks,
                registrar=registrar,  # type: ignore[arg-type]
                engine=engine,  # type: ignore[arg-type]
                history=HistoryService(
                    repos.executions,
                    repos.conversations,
                    retention_days=30,
                    chat_memory_hours=24,
                    clock=lambda: NOW,
                ),
                monitor=FakeMonitor(),  # type: ignore[arg-type]
                clock=lambda: NOW,
            ),
            settings=repos.settings,
            liveness_at="08:00",
            clock=lambda: NOW,
        )

    async def two_boots() -> None:
        # Ogni avvio è un processo nuovo: nuova istanza di C-39 sullo stesso DB.
        notifier = RestartNotifier(
            notifications, at="08:00", clock=lambda: NOW  # type: ignore[arg-type]
        )
        for _ in range(2):
            summary = await make_boot().on_start()
            await notifier.notify_restart(
                summary, summary.offline_period, summary.liveness_missed
            )

    asyncio.run(two_boots())

    assert engine.calls == 1
    assert len(notifications.texts) == 2


def test_failed_restart_is_not_retried(env) -> None:
    repos, notifications, _engine, run_boot, _liveness = env
    notifications.fail = True
    repos.settings.set(
        LAST_START_AT, (NOW - timedelta(hours=2)).isoformat(timespec="seconds")
    )

    asyncio.run(run_boot())

    assert notifications.calls == 1
