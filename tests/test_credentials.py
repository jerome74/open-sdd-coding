"""C-38 e callback C-05: classificazione degli errori di credenziale (spec 10)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
import pytest

from agente.config import DeepSeekConfig
from agente.alerts import AlertService
from agente.credential_monitor import CredentialMonitor
from agente.errors import LLMCredentialsError
from agente.llm import LLMClient
from agente.storage.db import Database
from agente.storage.repositories import repositories


class FakeAlerts:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []
        self.default_loop_missing = False

    def alert_threadsafe(self, kind: str, detail: dict):
        self.sent.append((kind, detail))
        return None


def _client(handler, monitor=None) -> LLMClient:
    config = DeepSeekConfig(
        model="deepseek-flash",
        api_base="https://deepseek.test/v1",
        api_key="secret-key",
        max_context_tokens=1000,
    )
    return LLMClient(
        config,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_attempts=1,
        retry_delay_s=0,
        sleep=lambda _s: None,
        on_credentials_error=None if monitor is None else monitor.on_llm_error,
    )


@pytest.mark.parametrize(
    ("status", "reason"),
    [(401, "chiave non valida"), (402, "credito esaurito"), (403, "accesso negato")],
)
def test_credential_statuses_are_classified(status: int, reason: str) -> None:
    alerts = FakeAlerts()
    monitor = CredentialMonitor(alerts)  # type: ignore[arg-type]

    assert monitor.on_llm_error(status, "body") is True
    assert alerts.sent == [("credential", {"status": status})]


@pytest.mark.parametrize("status", [400, 429, 500])
def test_transient_status_is_ignored(status: int) -> None:
    alerts = FakeAlerts()
    monitor = CredentialMonitor(alerts)  # type: ignore[arg-type]

    assert monitor.on_llm_error(status, "body") is False
    assert alerts.sent == []


class FakeNotifications:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def alert_admin(self, text: str) -> None:
        self.texts.append(text)


def test_credential_is_produced_once(tmp_path) -> None:
    db = Database(tmp_path / "credential.db")
    db.migrate()
    repos = repositories(db.connection)
    notifications = FakeNotifications()
    alerts = AlertService(
        notifications,
        repos.settings,
        clock=lambda: datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc),
    )
    monitor = CredentialMonitor(alerts)

    async def scenario() -> None:
        alerts.bind_loop(asyncio.get_running_loop())
        monitor.on_llm_error(402, "")
        monitor.on_llm_error(402, "")
        await asyncio.sleep(0.05)

    asyncio.run(scenario())

    assert len(notifications.texts) == 1
    db.close()


def test_body_is_not_logged(caplog) -> None:
    alerts = FakeAlerts()
    monitor = CredentialMonitor(alerts)  # type: ignore[arg-type]

    with caplog.at_level(logging.DEBUG, logger="agente.credential_monitor"):
        monitor.on_llm_error(402, "contenuto-segreto")

    assert "contenuto-segreto" not in caplog.text


def test_logs_status_only(caplog) -> None:
    alerts = FakeAlerts()
    monitor = CredentialMonitor(alerts)  # type: ignore[arg-type]

    with caplog.at_level(logging.WARNING, logger="agente.credential_monitor"):
        monitor.on_llm_error(401)

    assert caplog.records[0].status == 401


def test_credentials_error_calls_the_monitor() -> None:
    alerts = FakeAlerts()
    monitor = CredentialMonitor(alerts)  # type: ignore[arg-type]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"error": "insufficient balance"})

    with pytest.raises(LLMCredentialsError) as excinfo:
        _client(handler, monitor).chat([{"role": "user", "content": "x"}])

    assert excinfo.value.status == 402
    assert alerts.sent == [("credential", {"status": 402})]


def test_credentials_error_without_monitor_is_unchanged() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid"})

    with pytest.raises(LLMCredentialsError) as excinfo:
        _client(handler).chat([{"role": "user", "content": "x"}])

    assert excinfo.value.status == 401


def test_secret_never_appears_in_error_message() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid"})

    with pytest.raises(LLMCredentialsError) as excinfo:
        _client(handler).chat([{"role": "user", "content": "x"}])

    assert "secret-key" not in str(excinfo.value)


def test_logs_invalid_status(caplog) -> None:
    alerts = FakeAlerts()
    monitor = CredentialMonitor(alerts)  # type: ignore[arg-type]

    with caplog.at_level(logging.WARNING, logger="agente.credential_monitor"):
        assert monitor.on_llm_error("boh") is False

    assert any(record.message == "status HTTP non valido" for record in caplog.records)
