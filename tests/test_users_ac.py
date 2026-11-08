"""AC-01…AC-05 di spec 08, end-to-end sull'applicazione con dipendenze finte."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import pytest

from agente.app import AgentApp
from agente.llm import LLMResponse
from agente.storage.repositories import User
from agente.telegram_gateway import IncomingMessage
from conftest import ADMIN_ID, USER_ID
from test_scheduled_ac import AppScheduler

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
STRANGER = 900


class Gateway:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []
        self.deleted: list[tuple[int, int]] = []
        self._next_id = 0

    async def send(self, chat_id, text, keyboard=None) -> int:
        self._next_id += 1
        self.sent.append((chat_id, text, keyboard))
        return self._next_id

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))

    def texts(self) -> list[str]:
        return [text for _, text, _ in self.sent]

    def to(self, chat_id: int) -> list[str]:
        return [text for target, text, _ in self.sent if target == chat_id]

    def last(self) -> str:
        return self.sent[-1][1]


class StubLLM:
    def chat(self, messages, tools=None):
        return LLMResponse(text="")

    def summarize(self, text: str) -> str:
        return text


def message(text: str = "", *, user: int, callback: str | None = None, username=None):
    return IncomingMessage(
        user_id=user,
        chat_id=user,
        text=text,
        callback_data=callback,
        username=username,
    )


@pytest.fixture
def app(make_config) -> AgentApp:
    config = make_config(admin_id=ADMIN_ID)
    built = AgentApp.build(
        config,
        gateway=Gateway(),
        scheduler=AppScheduler(),
        llm=StubLLM(),
        clock=lambda: NOW,
    )
    built.db.migrate()
    yield built
    built.db.close()


def test_ac01_unknown_is_refused_and_admin_is_alerted(app: AgentApp) -> None:
    result = asyncio.run(
        app.router.route(message("ciao", user=STRANGER, username="mario"))
    )

    assert result.kind == "ignored"
    assert app.gateway.to(STRANGER) == ["Non sei autorizzato a usare questo agente."]
    alerts = app.gateway.to(ADMIN_ID)
    assert any("Nuovo contatto" in text and "@mario" in text for text in alerts)
    alert_keyboard = [
        keyboard
        for chat_id, text, keyboard in app.gateway.sent
        if chat_id == ADMIN_ID and "Nuovo contatto" in text
    ][0]
    assert alert_keyboard == ((("Autorizza", f"authorize:{STRANGER}"),),)


def test_ac02_authorized_user_accepts_and_uses_the_agent(app: AgentApp) -> None:
    asyncio.run(app.router.route(message("ciao", user=STRANGER, username="mario")))
    asyncio.run(
        app.router.route(message("", user=ADMIN_ID, callback=f"authorize:{STRANGER}"))
    )

    pending = app.repos.users.get(STRANGER)
    assert pending.state == "pending"
    assert any("Privacy" in text for text in app.gateway.to(STRANGER))

    asyncio.run(
        app.router.route(message("", user=STRANGER, callback="consent:accept"))
    )
    accepted = app.repos.users.get(STRANGER)
    assert accepted.state == "accepted"
    assert accepted.consent_at == NOW.isoformat(timespec="seconds")

    action = asyncio.run(app.router.route(message("/tasks", user=STRANGER)))

    assert action.kind == "listed"
    assert app.gateway.to(STRANGER)[-1] == "Nessun compito."


def test_ac03_declined_consent_keeps_the_user_unauthorized(app: AgentApp) -> None:
    asyncio.run(app.router.route(message("ciao", user=STRANGER, username="mario")))
    asyncio.run(
        app.router.route(message("", user=ADMIN_ID, callback=f"authorize:{STRANGER}"))
    )

    asyncio.run(
        app.router.route(message("", user=STRANGER, callback="consent:decline"))
    )

    assert app.repos.users.get(STRANGER).state == "revoked"
    assert app.repos.users.get(STRANGER).consent_at is None
    assert any(
        "ha rifiutato l'informativa" in text for text in app.gateway.to(ADMIN_ID)
    )
    action = asyncio.run(app.router.route(message("ciao", user=STRANGER)))
    assert action.kind == "ignored"
    assert app.gateway.to(STRANGER)[-1] == "Non sei autorizzato a usare questo agente."


def test_ac04_revoked_user_is_ignored(app: AgentApp) -> None:
    app.repos.users.upsert(User(telegram_id=USER_ID, username="utente", state="accepted"))

    asyncio.run(app.router.route(message(f"/removeuser {USER_ID}", user=ADMIN_ID)))
    assert app.repos.users.get(USER_ID).state == "revoked"

    action = asyncio.run(app.router.route(message("ciao", user=USER_ID)))

    assert action.kind == "ignored"
    assert app.gateway.to(USER_ID)[-1] == "Non sei autorizzato a usare questo agente."


def test_ac05_authorized_user_cannot_add_users(app: AgentApp) -> None:
    app.repos.users.upsert(User(telegram_id=USER_ID, username="utente", state="accepted"))

    action = asyncio.run(
        app.router.route(message("/adduser 777 mario", user=USER_ID))
    )

    assert action.kind == "rejected"
    assert app.repos.users.get(777) is None
    assert app.gateway.last() == "Solo l'amministratore può gestire gli utenti."


def test_pending_user_stays_pending_until_acceptance(app: AgentApp) -> None:
    asyncio.run(app.router.route(message("ciao", user=STRANGER, username="mario")))
    asyncio.run(
        app.router.route(message("", user=ADMIN_ID, callback=f"authorize:{STRANGER}"))
    )

    action = asyncio.run(app.router.route(message("/tasks", user=STRANGER)))

    assert action.kind == "ignored"
    assert app.repos.users.get(STRANGER).state == "pending"
    assert app.gateway.to(STRANGER)[-1] == "Non sei autorizzato a usare questo agente."


def test_pending_user_contact_alerts_the_admin_once(app: AgentApp) -> None:
    asyncio.run(app.router.route(message("/adduser 55 mario", user=ADMIN_ID)))
    alerts_before = [
        text
        for chat_id, text, _ in app.gateway.sent
        if chat_id == ADMIN_ID and "Nuovo contatto" in text
    ]
    assert alerts_before == []

    action = asyncio.run(app.router.route(message("ciao", user=55, username="mario")))

    assert action.kind == "ignored"
    assert app.repos.users.get(55).state == "pending"
    alerts = [
        text
        for chat_id, text, _ in app.gateway.sent
        if chat_id == ADMIN_ID and "Nuovo contatto" in text
    ]
    assert len(alerts) == 1
    assert "@mario" in alerts[0]
