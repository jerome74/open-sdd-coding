"""C-33: avviso all'admin e antispam sui contatti sconosciuti (spec 08)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from agente.authorization_notifier import (
    UNKNOWN_ALERT_WINDOW_S,
    AuthorizationNotifier,
)
from agente.errors import TelegramError
from agente.notifications import NotificationService
from agente.storage.db import Database
from agente.storage.repositories import repositories

ADMIN = 1
NOW = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


class Gateway:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []
        self.fail = False

    async def send(self, chat_id, text, keyboard=None) -> None:
        if self.fail:
            raise TelegramError("rete")
        self.sent.append((chat_id, text, keyboard))

    def texts(self) -> list[str]:
        return [text for _, text, _ in self.sent]


@pytest.fixture
def env(tmp_path, make_config):
    db = Database(tmp_path / "notifier.db")
    db.migrate()
    repos = repositories(db.connection)
    gateway = Gateway()
    clock = Clock(NOW)
    config = make_config(admin_id=ADMIN)
    notifications = NotificationService(gateway, config, repos.approvals)
    notifier = AuthorizationNotifier(notifications, clock=clock)
    yield notifier, gateway, clock
    db.close()


def test_alert_has_authorize_button_and_username(env) -> None:
    notifier, gateway, _clock = env

    assert asyncio.run(notifier.notify_unknown(42, "mario")) is True

    chat_id, text, keyboard = gateway.sent[0]
    assert chat_id == ADMIN
    assert "@mario" in text and "42" in text
    assert keyboard == ((("Autorizza", "authorize:42"),),)


def test_alert_without_username_uses_the_id(env) -> None:
    notifier, gateway, _clock = env

    asyncio.run(notifier.notify_unknown(42, None))

    assert "id 42" in gateway.sent[0][1]


def test_second_contact_within_the_window_is_suppressed(env) -> None:
    notifier, gateway, clock = env

    asyncio.run(notifier.notify_unknown(42, "mario"))
    clock.moment = NOW + timedelta(hours=23)
    suppressed = asyncio.run(notifier.notify_unknown(42, "mario"))

    assert suppressed is False
    assert len(gateway.sent) == 1


def test_alert_resumes_after_the_window(env) -> None:
    notifier, gateway, clock = env

    asyncio.run(notifier.notify_unknown(42, "mario"))
    clock.moment = NOW + timedelta(seconds=UNKNOWN_ALERT_WINDOW_S + 1)

    assert asyncio.run(notifier.notify_unknown(42, "mario")) is True
    assert len(gateway.sent) == 2


def test_users_are_independent(env) -> None:
    notifier, gateway, _clock = env

    asyncio.run(notifier.notify_unknown(42, "mario"))
    asyncio.run(notifier.notify_unknown(43, "anna"))

    assert len(gateway.sent) == 2


def test_username_is_kept_for_the_callback(env) -> None:
    notifier, _gateway, _clock = env

    asyncio.run(notifier.notify_unknown(42, "mario"))

    assert notifier.username_for(42) == "mario"
    assert notifier.username_for(99) is None


def test_failed_alert_does_not_advance_the_window(env) -> None:
    notifier, gateway, clock = env
    gateway.fail = True

    assert asyncio.run(notifier.notify_unknown(42, "mario")) is False

    gateway.fail = False
    clock.moment = NOW + timedelta(minutes=1)
    assert asyncio.run(notifier.notify_unknown(42, "mario")) is True
    assert len(gateway.sent) == 1
