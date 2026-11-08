"""C-40: segnale di vita, marcatore e osservabilità (spec 11)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import pytest

from agente.errors import TelegramError
from agente.liveness import LIVENESS_MARKER, LivenessScheduler
from agente.storage.db import Database
from agente.storage.repositories import repositories

NOW = datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc)


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


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "liveness.db")
    db.migrate()
    repos = repositories(db.connection)
    notifications = FakeNotifications()
    scheduler = LivenessScheduler(
        notifications,  # type: ignore[arg-type]
        repos.settings,
        at="08:00",
        clock=lambda: NOW,
    )
    yield scheduler, notifications, repos.settings
    db.close()


def test_liveness_sends_and_marks(env) -> None:
    scheduler, notifications, settings = env

    assert asyncio.run(scheduler.send_liveness()) is True

    assert notifications.texts == ["✅ Segnale di vita: tutto ok (08:00)."]
    assert settings.get(LIVENESS_MARKER) == NOW.isoformat(timespec="seconds")


def test_liveness_failure_keeps_marker(env) -> None:
    scheduler, notifications, settings = env
    notifications.fail = True

    assert asyncio.run(scheduler.send_liveness()) is False

    assert settings.get(LIVENESS_MARKER) is None
    assert notifications.texts == []


def test_liveness_text(env) -> None:
    _scheduler, _notifications, _settings = env
    notifications = FakeNotifications()
    scheduler = LivenessScheduler(
        notifications,  # type: ignore[arg-type]
        _settings,
        at="7:05",
        clock=lambda: NOW,
    )

    asyncio.run(scheduler.send_liveness())

    assert notifications.texts == ["✅ Segnale di vita: tutto ok (07:05)."]


def test_liveness_goes_only_to_admin(env) -> None:
    scheduler, notifications, _settings = env

    asyncio.run(scheduler.send_liveness())

    # C-10 espone solo alert_admin: nessun destinatario arbitrario.
    assert notifications.calls == 1
    assert notifications.texts


def test_liveness_logs_send_and_failure(env, caplog) -> None:
    scheduler, notifications, _settings = env

    with caplog.at_level(logging.INFO, logger="agente.liveness"):
        asyncio.run(scheduler.send_liveness())
    assert any(r.message == "segnale di vita inviato" for r in caplog.records)

    notifications.fail = True
    with caplog.at_level(logging.ERROR, logger="agente.liveness"):
        asyncio.run(scheduler.send_liveness())
    assert any(
        r.message == "segnale di vita non inviato" for r in caplog.records
    )
