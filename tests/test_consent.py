"""C-32: informativa privacy, accettazione e rifiuto (spec 08, BR-18)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from agente.consent import PRIVACY_NOTICE, ConsentFlow
from agente.errors import TelegramError, UserAccessError
from agente.notifications import NotificationService
from agente.storage.db import Database
from agente.storage.repositories import User, repositories
from agente.user_state import MAX_AUTHORIZED_USERS

ADMIN = 1
USER = 2
NOW = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)


class Gateway:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []
        self.fail = False
        self.fail_chats: set[int] = set()

    async def send(self, chat_id, text, keyboard=None) -> None:
        if self.fail or chat_id in self.fail_chats:
            raise TelegramError("rete")
        self.sent.append((chat_id, text, keyboard))

    def texts(self) -> list[str]:
        return [text for _, text, _ in self.sent]


@pytest.fixture
def env(tmp_path, make_config):
    db = Database(tmp_path / "consent.db")
    db.migrate()
    repos = repositories(db.connection)
    gateway = Gateway()
    config = make_config(admin_id=ADMIN)
    notifications = NotificationService(gateway, config, repos.approvals)
    flow = ConsentFlow(repos.users, notifications, clock=lambda: NOW)
    yield flow, repos, gateway
    db.close()


def _pending(repos, telegram_id: int = USER, username: str | None = "utente") -> User:
    return repos.users.upsert(
        User(telegram_id=telegram_id, username=username, state="pending")
    )


def test_send_consent_has_notice_and_buttons(env) -> None:
    flow, repos, gateway = env
    _pending(repos)

    assert asyncio.run(flow.send_consent(USER)) is True

    chat_id, text, keyboard = gateway.sent[0]
    assert chat_id == USER
    assert text == PRIVACY_NOTICE
    assert "DeepSeek" in text and "S24" in text
    buttons = [button for row in keyboard for button in row]
    assert [label for label, _ in buttons] == ["Accetto", "Rifiuto"]
    assert [data for _, data in buttons] == ["consent:accept", "consent:decline"]


def test_accept_enables_the_user(env) -> None:
    flow, repos, _gateway = env
    _pending(repos)

    result = asyncio.run(flow.accept(USER, by_user_id=USER))

    assert result.changed is True
    assert result.user.state == "accepted"
    assert result.user.consent_at == NOW.isoformat(timespec="seconds")
    assert "autorizzato" in result.note


def test_accept_reports_the_change(env) -> None:
    flow, repos, _gateway = env
    _pending(repos)

    result = asyncio.run(flow.accept(USER, by_user_id=USER))

    assert result.changed is True
    assert result.notice_sent is False


def test_another_user_cannot_accept(env) -> None:
    flow, repos, _gateway = env
    _pending(repos)

    with pytest.raises(UserAccessError) as caught:
        asyncio.run(flow.accept(USER, by_user_id=99))

    assert caught.value.reason == "invalid_target"
    assert repos.users.get(USER).state == "pending"


def test_accept_requires_a_pending_user(env) -> None:
    flow, repos, _gateway = env
    repos.users.upsert(User(telegram_id=USER, state="accepted"))

    with pytest.raises(UserAccessError) as caught:
        asyncio.run(flow.accept(USER, by_user_id=USER))

    assert caught.value.reason == "invalid_state"


def test_accept_unknown_user_is_not_found(env) -> None:
    flow, _repos, _gateway = env

    with pytest.raises(UserAccessError) as caught:
        asyncio.run(flow.accept(404, by_user_id=404))

    assert caught.value.reason == "not_found"


def test_acceptance_is_refused_when_the_limit_is_reached(env) -> None:
    flow, repos, gateway = env
    for index in range(MAX_AUTHORIZED_USERS):
        repos.users.upsert(
            User(telegram_id=100 + index, state="accepted", consent_at=NOW.isoformat())
        )
    _pending(repos)

    with pytest.raises(UserAccessError) as caught:
        asyncio.run(flow.accept(USER, by_user_id=USER))

    assert caught.value.reason == "limit"
    assert repos.users.get(USER).state == "pending"
    assert any("Limite di 5" in text for text in gateway.texts())


def test_decline_revokes_and_alerts_the_admin(env) -> None:
    flow, repos, gateway = env
    _pending(repos)

    result = asyncio.run(flow.decline(USER, by_user_id=USER))

    assert result.changed is True
    assert result.user.state == "revoked"
    assert result.user.consent_at is None
    alert = gateway.sent[-1]
    assert alert[0] == ADMIN
    assert "ha rifiutato l'informativa" in alert[1]
    assert "@utente" in alert[1]


def test_decline_requires_a_pending_user(env) -> None:
    flow, repos, _gateway = env
    repos.users.upsert(User(telegram_id=USER, state="revoked"))

    with pytest.raises(UserAccessError) as caught:
        asyncio.run(flow.decline(USER, by_user_id=USER))

    assert caught.value.reason == "invalid_state"


def test_failed_notice_keeps_the_user_pending(env) -> None:
    flow, repos, gateway = env
    _pending(repos)
    gateway.fail_chats = {USER}

    assert asyncio.run(flow.send_consent(USER)) is False

    assert repos.users.get(USER).state == "pending"
    assert gateway.sent[-1][0] == ADMIN
    assert "non inviata" in gateway.sent[-1][1]
