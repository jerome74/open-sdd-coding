"""Criteri di accettazione AC-01…AC-04 di spec 02, end-to-end sul router."""

from __future__ import annotations

import asyncio

from agente.telegram_gateway import IncomingMessage
from conftest import ADMIN_ID, USER_ID, FakeLLM


def message(text: str, *, user: int = ADMIN_ID) -> IncomingMessage:
    return IncomingMessage(user_id=user, chat_id=user, text=text)


def creation_llm(schedule_text: str = "ogni giorno alle 8") -> FakeLLM:
    return FakeLLM(
        draft={
            "name": "rassegna",
            "instructions": "riassumi i titoli principali",
            "schedule": schedule_text,
            "recipients": [],
            "log_allowlist": [],
        }
    )


def test_ac01_summary_then_save_only_after_confirmation(harness_factory) -> None:
    harness = harness_factory(llm=creation_llm())

    async def scenario() -> list[int]:
        routing = asyncio.create_task(
            harness.router.route(
                message("ogni giorno alle 8 riassumi i titoli principali, chiamalo rassegna")
            )
        )
        while not harness.confirmations.pending():
            await asyncio.sleep(0.01)
        before = harness.repos.tasks.list()
        harness.confirmations.resolve(
            harness.confirmations.pending()[0], True, by_user_id=ADMIN_ID
        )
        action = await routing
        assert action.kind == "created"
        return before

    before = asyncio.run(scenario())

    assert before == []
    tasks = harness.repos.tasks.list()
    assert [task.name for task in tasks] == ["rassegna"]
    assert tasks[0].state == "active"
    assert (tasks[0].schedule_type, tasks[0].schedule_expr) == ("orario", "08:00")

    summary = harness.gateway.sent[0][1]
    for fragment in ("Nome: rassegna", "Istruzioni: riassumi i titoli principali",
                     "Orario: ogni giorno alle 08:00", "Destinatari: solo amministratore"):
        assert fragment in summary
    assert "creato e attivo" in harness.gateway.last()


def test_ac02_ambiguous_time_is_asked_not_assumed(harness_factory) -> None:
    harness = harness_factory(llm=creation_llm(schedule_text="la mattina"))

    async def scenario() -> str:
        action = await harness.router.route(
            message("la mattina riassumi i titoli, chiamalo rassegna")
        )
        return action.kind

    assert asyncio.run(scenario()) == "ask_schedule"
    assert harness.repos.tasks.list() == []
    assert "A che ora esattamente" in harness.gateway.last()
    assert harness.confirmations.pending() == []


def test_ac03_authorized_user_is_refused_without_side_effects(harness_factory) -> None:
    harness = harness_factory(llm=creation_llm())

    async def scenario() -> str:
        action = await harness.router.route(
            message("ogni giorno alle 8 riassumi i titoli", user=USER_ID)
        )
        return action.kind

    assert asyncio.run(scenario()) == "rejected"
    assert harness.repos.tasks.list() == []
    # D1: la bozza viene estratta per distinguere creazione e chat; nessun
    # compito viene creato e nessuna conferma viene chiesta.
    assert harness.llm.calls == 1
    assert harness.confirmations.pending() == []
    assert "Solo l'amministratore" in harness.gateway.last()


def test_ac04_pause_stops_execution_until_resume(harness_factory) -> None:
    harness = harness_factory()
    from agente.schedule_interpreter import Schedule
    from agente.task_manager import TaskDraft

    task = harness.manager.create(
        TaskDraft(name="rassegna", instructions="riassumi", schedule=Schedule("orario", "08:00"))
    )
    harness.gateway.sent.clear()
    harness.registrar.unscheduled.clear()
    harness.registrar.scheduled.clear()

    async def scenario() -> None:
        routing = asyncio.create_task(harness.router.route(message("/pause rassegna")))
        while not harness.confirmations.pending():
            await asyncio.sleep(0.01)
        harness.confirmations.resolve(
            harness.confirmations.pending()[0], True, by_user_id=ADMIN_ID
        )
        await routing

    asyncio.run(scenario())
    assert harness.repos.tasks.get(task.id).state == "paused"
    assert harness.registrar.unscheduled == [task.id]
    assert harness.registrar.scheduled == []
    assert "sospeso" in harness.gateway.last()
