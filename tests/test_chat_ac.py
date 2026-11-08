"""AC-01…AC-06 di spec 05, end-to-end sul router con dipendenze finte."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone

from agente.llm import LLMResponse
from agente.telegram_gateway import IncomingMessage
from conftest import ADMIN_ID, USER_ID

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def message(text: str, *, user: int = USER_ID) -> IncomingMessage:
    return IncomingMessage(user_id=user, chat_id=user, text=text)


class ChatLLM:
    """C-05 finto: bozza incompleta per l'admin, risposte testuali per la chat."""

    def __init__(self, answers: list[str] | None = None, *, delay: float = 0.0) -> None:
        self.answers = list(answers or [])
        self.delay = delay
        self.chat_calls: list[list[dict]] = []

    def chat(self, messages, tools=None):
        system = str(messages[0].get("content", ""))
        if "Estrai i campi" in system:
            return LLMResponse(text=json.dumps({}))
        if self.delay:
            time.sleep(self.delay)
        self.chat_calls.append([dict(item) for item in messages])
        if self.answers:
            return LLMResponse(text=self.answers.pop(0))
        return LLMResponse(text="risposta")


def test_ac01_second_question_uses_the_previous_turn(harness_factory) -> None:
    llm = ChatLLM(["sereno", "domani piove"])
    harness = harness_factory(llm=llm)

    async def scenario() -> list[str]:
        first = await harness.router.route(message("che tempo fa?"))
        second = await harness.router.route(message("e domani?"))
        return [first.kind, second.kind]

    assert asyncio.run(scenario()) == ["answered", "answered"]
    second = llm.chat_calls[1]
    assert {"role": "user", "content": "che tempo fa?"} in second
    assert {"role": "assistant", "content": "sereno"} in second


def test_ac02_silence_resets_the_context(harness_factory) -> None:
    now = [NOW]
    llm = ChatLLM(["prima risposta", "seconda risposta"])
    harness = harness_factory(llm=llm, clock=lambda: now[0])

    async def scenario() -> None:
        await harness.router.route(message("prima domanda"))
        now[0] = NOW + timedelta(hours=25)
        await harness.router.route(message("dopo il silenzio"))

    asyncio.run(scenario())

    second = llm.chat_calls[1]
    assert {"role": "user", "content": "prima domanda"} not in second
    assert {"role": "assistant", "content": "prima risposta"} not in second


def test_ac03_reset_starts_from_scratch(harness_factory) -> None:
    llm = ChatLLM(["prima risposta", "seconda risposta"])
    harness = harness_factory(llm=llm)

    async def scenario() -> str:
        await harness.router.route(message("prima domanda"))
        reset = await harness.router.route(message("/reset"))
        assert reset.kind == "reset"
        await harness.router.route(message("nuova domanda"))
        return reset.kind

    asyncio.run(scenario())

    second = llm.chat_calls[1]
    assert {"role": "user", "content": "prima domanda"} not in second
    assert harness.gateway.texts()[-2] == "Conversazione azzerata."


def test_ac04_admin_reads_an_authorized_user_chat(harness_factory) -> None:
    harness = harness_factory(llm=ChatLLM(["risposta dell'utente"]))

    async def scenario() -> str:
        await harness.router.route(message("domanda riservata"))
        action = await harness.router.route(
            message(f"/chat {USER_ID}", user=ADMIN_ID)
        )
        return action.kind

    assert asyncio.run(scenario()) == "transcript"
    reply = harness.gateway.last()
    assert f"Conversazione di {USER_ID}" in reply
    assert "domanda riservata" in reply
    assert "risposta dell'utente" in reply


def test_ac04_authorized_user_cannot_read_chats(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(message(f"/chat {USER_ID}", user=USER_ID))
        return action.kind

    assert asyncio.run(scenario()) == "rejected"
    assert "Solo l'amministratore" in harness.gateway.last()


def test_ac05_simple_question_gets_an_answer_without_indicator(harness_factory) -> None:
    harness = harness_factory(llm=ChatLLM(["risposta semplice"]))

    async def scenario() -> str:
        action = await harness.router.route(message("domanda semplice"))
        return action.kind

    assert asyncio.run(scenario()) == "answered"
    assert harness.gateway.last() == "risposta semplice"
    assert "sto cercando…" not in harness.gateway.texts()
    # D7: nessun timeout rigido a 30 s; la latenza è un obiettivo (P-A-18).
    assert harness.gateway.deleted == []


def test_ac06_slow_answer_shows_and_removes_the_indicator(harness_factory) -> None:
    harness = harness_factory(llm=ChatLLM(["risposta lenta"], delay=1.05), chat_progress_s=1)

    async def scenario() -> str:
        action = await harness.router.route(message("domanda lenta"))
        return action.kind

    assert asyncio.run(scenario()) == "answered"
    assert "sto cercando…" in harness.gateway.texts()
    assert harness.gateway.deleted, "l'indicatore deve essere eliminato alla risposta"
    assert harness.gateway.last() == "risposta lenta"


def test_admin_chat_does_not_create_a_task(harness_factory) -> None:
    harness = harness_factory(llm=ChatLLM(["risposta"]))

    async def scenario() -> str:
        action = await harness.router.route(message("qual è il meteo?", user=ADMIN_ID))
        return action.kind

    assert asyncio.run(scenario()) == "answered"
    assert harness.repos.tasks.list() == []
    assert harness.confirmations.pending() == []


def test_app_wiring_answers_a_chat_and_runs_maintenance(make_config) -> None:
    from test_scheduled_ac import build_app

    app = build_app(make_config)
    app.gateway.sent.clear()

    action = asyncio.run(app.router.route(message("ciao")))
    app._maintenance()

    assert action.kind == "answered"
    assert app.gateway.sent[-1][0] == USER_ID
    app.db.close()
