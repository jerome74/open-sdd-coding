"""AC-01…AC-04 di spec 10, con dipendenze esterne finte."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from agente.alerts import AlertService
from agente.config import DeepSeekConfig
from agente.credential_monitor import CredentialMonitor
from agente.device_monitor import DeviceMonitor
from agente.errors import DeviceError, LLMError
from agente.execution import ExecutionEngine
from agente.history import HistoryService
from agente.llm import LLMClient
from agente.recovery import RecoveryHandler
from agente.storage.db import Database
from agente.storage.repositories import Task, repositories

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


class FakeNotifications:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def alert_admin(self, text: str) -> None:
        self.texts.append(text)


class FakeLLM:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def chat(self, messages, tools=None):
        if self.error is not None:
            raise self.error
        raise AssertionError("risposta non attesa")


class FakeDevice:
    def __init__(self, *, battery: int = 50, online: bool = True) -> None:
        self.battery = battery
        self.online = online

    def battery_level(self) -> int:
        return self.battery

    def is_online(self) -> bool:
        return self.online

    def record_last_contact(self, settings, when=None) -> str:
        moment = (when or NOW).isoformat(timespec="seconds")
        settings.set("last_contact_at", moment)
        return moment


class FakeRegistrar:
    def __init__(self) -> None:
        self.markers: dict[int, datetime] = {}

    def next_run(self, task_id: int):
        return self.markers.get(task_id)

    def update(self, task) -> None:
        self.markers[task.id] = NOW + timedelta(days=1)


class FakeEngine:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def execute(self, task, trigger: str, requester=None):
        from agente.execution import ExecutionResult

        self.calls.append(task.id)
        moment = NOW.isoformat(timespec="seconds")
        return ExecutionResult(
            execution_id=len(self.calls),
            task_id=task.id,
            outcome="ok",
            started_at=moment,
            finished_at=moment,
            summary="ok",
            text="ok",
        )


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "alerts_ac.db")
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
    alerts = AlertService(notifications, repos.settings, clock=lambda: NOW)
    task = repos.tasks.create(
        Task(
            name="news",
            instructions="riassumi",
            schedule_type="orario",
            schedule_expr="08:00",
            created_by=1,
        )
    )
    yield repos, history, notifications, alerts, task
    db.close()


def test_ac01_failed_task_alerts_admin(env) -> None:
    _repos, history, notifications, alerts, task = env
    engine = ExecutionEngine(
        FakeLLM(LLMError("boom")),  # type: ignore[arg-type]
        history,
        notifications,  # type: ignore[arg-type]
        timeout_s=10,
        alerts=alerts,
    )

    result = asyncio.run(engine.execute(task, "scheduled"))

    assert result.outcome == "errore"
    assert len(notifications.texts) == 1
    assert "news" in notifications.texts[0]
    assert "LLMError" in notifications.texts[0]


def test_ac02_low_battery_alerts_admin(env) -> None:
    _repos, _history, notifications, alerts, _task = env
    monitor = DeviceMonitor(
        FakeDevice(battery=14),  # type: ignore[arg-type]
        _repos.settings,
        alerts,
        battery_threshold_pct=15,
        offline_threshold_s=3600,
        clock=lambda: NOW,
    )

    asyncio.run(monitor.check_battery())

    assert notifications.texts == ["🔋 Batteria al 14% (soglia 15%)"]


def test_ac03_offline_period_alerts_on_return(env) -> None:
    repos, history, notifications, alerts, task = env
    monitor = DeviceMonitor(
        FakeDevice(online=True),  # type: ignore[arg-type]
        repos.settings,
        alerts,
        battery_threshold_pct=15,
        offline_threshold_s=3600,
        clock=lambda: NOW,
    )
    recovery = RecoveryHandler(
        tasks=repos.tasks,
        registrar=FakeRegistrar(),  # type: ignore[arg-type]
        engine=FakeEngine(),  # type: ignore[arg-type]
        history=history,
        monitor=monitor,
        clock=lambda: NOW,
    )
    recovery._registrar.markers[task.id] = NOW - timedelta(days=1)  # type: ignore[attr-defined]
    repos.settings.set("offline_since", (NOW - timedelta(hours=2)).isoformat())

    results = asyncio.run(recovery.check_connectivity())

    assert len(results) == 1
    assert len(notifications.texts) == 1
    assert "2 h" in notifications.texts[0]
    assert "offline dalle" in notifications.texts[0]


def test_ac04_credential_error_alerts_admin(env) -> None:
    _repos, _history, notifications, alerts, _task = env
    monitor = CredentialMonitor(alerts)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"error": "insufficient balance"})

    config = DeepSeekConfig(
        model="deepseek-flash",
        api_base="https://deepseek.test/v1",
        api_key="secret-key",
        max_context_tokens=1000,
    )
    client = LLMClient(
        config,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_attempts=1,
        retry_delay_s=0,
        sleep=lambda _s: None,
        on_credentials_error=monitor.on_llm_error,
    )

    async def scenario() -> None:
        alerts.bind_loop(asyncio.get_running_loop())
        try:
            await asyncio.to_thread(
                client.chat, [{"role": "user", "content": "x"}]
            )
        except Exception:
            pass
        await asyncio.sleep(0.05)

    asyncio.run(scenario())

    assert len(notifications.texts) == 1
    assert "credito esaurito" in notifications.texts[0]
    assert "HTTP 402" in notifications.texts[0]


def test_no_restart_or_liveness_message(env) -> None:
    _repos, _history, notifications, alerts, _task = env
    monitor = DeviceMonitor(
        FakeDevice(battery=14),  # type: ignore[arg-type]
        _repos.settings,
        alerts,
        battery_threshold_pct=15,
        offline_threshold_s=3600,
        clock=lambda: NOW,
    )

    asyncio.run(monitor.check_battery())

    assert not any("Sono di nuovo attivo" in text for text in notifications.texts)
    assert not any("tutto ok" in text.lower() for text in notifications.texts)
