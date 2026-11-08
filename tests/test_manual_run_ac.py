"""AC-01…AC-03 di spec 04, end-to-end sul router con dipendenze finte."""

from __future__ import annotations

import asyncio

from agente.app import AgentApp
from agente.errors import LLMError
from agente.schedule_interpreter import Schedule
from agente.storage.repositories import User
from agente.task_manager import TaskDraft
from agente.telegram_gateway import IncomingMessage
from conftest import ADMIN_ID, USER_ID
from test_scheduled_ac import AppDevice, AppGateway, AppLLM, AppScheduler


def message(text: str, *, user: int = ADMIN_ID) -> IncomingMessage:
    return IncomingMessage(user_id=user, chat_id=user, text=text)


class FailingLLM:
    """C-05 finto che fallisce: serve al messaggio di esito negativo (P-A-06)."""

    def chat(self, messages, tools=None):
        raise LLMError("modello non disponibile")

    def summarize(self, text: str) -> str:
        return text


def build_app(make_config, *, llm=None):
    config = make_config(admin_id=ADMIN_ID)
    app = AgentApp.build(
        config,
        gateway=AppGateway(),
        scheduler=AppScheduler(),
        llm=llm or AppLLM(),
        device=AppDevice(online=True),
    )
    app.db.migrate()
    app.repos.users.upsert(User(telegram_id=USER_ID, username="utente", state="accepted"))
    return app


def _task(app, name: str = "rassegna", *, recipients: tuple[int, ...] = ()):
    return app.tasks.create(
        TaskDraft(
            name=name,
            instructions="riassumi i titoli",
            schedule=Schedule("orario", "08:00"),
            recipients=recipients,
        )
    )


def test_ac01_subscriber_gets_the_result_alone(make_config) -> None:
    app = build_app(make_config)
    task = _task(app, recipients=(USER_ID,))
    app.gateway.sent.clear()

    action = asyncio.run(app.router.route(message("/run rassegna", user=USER_ID)))

    assert action.kind == "run"
    assert [chat_id for chat_id, _ in app.gateway.sent] == [USER_ID]
    assert app.gateway.sent[0][1] == "risultato settimanale"
    stored = app.repos.executions.list(task_id=task.id)
    assert [(row.trigger, row.requested_by, row.outcome) for row in stored] == [
        ("manual", USER_ID, "ok")
    ]
    app.db.close()


def test_ac01_admin_result_does_not_reach_the_subscribers(make_config) -> None:
    app = build_app(make_config)
    _task(app, recipients=(USER_ID,))
    app.gateway.sent.clear()

    asyncio.run(app.router.route(message("/run rassegna")))

    assert [chat_id for chat_id, _ in app.gateway.sent] == [ADMIN_ID]
    app.db.close()


def test_ac02_unsubscribed_user_is_refused(make_config) -> None:
    app = build_app(make_config)
    task = _task(app, name="log")
    app.gateway.sent.clear()

    action = asyncio.run(app.router.route(message("/run log", user=USER_ID)))

    assert action.kind == "rejected"
    assert "Non sei iscritto" in app.gateway.sent[-1][1]
    assert app.repos.executions.list(task_id=task.id) == []
    app.db.close()


def test_ac03_manual_launch_refused_while_scheduled_runs(make_config) -> None:
    app = build_app(make_config)
    task = _task(app)
    app.gateway.sent.clear()

    # Lock detenuto da un'esecuzione programmata in corso.
    assert app.lock.acquire(task.id) is True
    try:
        action = asyncio.run(app.router.route(message("/run rassegna")))
    finally:
        app.lock.release(task.id)

    assert action.kind == "rejected"
    assert "già in esecuzione" in app.gateway.sent[-1][1]
    assert app.repos.executions.list(task_id=task.id) == []
    assert app.lock.held(task.id) is False
    app.db.close()


def test_failed_manual_run_reports_the_status_to_the_requester(make_config) -> None:
    app = build_app(make_config, llm=FailingLLM())
    _task(app, recipients=(USER_ID,))
    app.gateway.sent.clear()

    asyncio.run(app.router.route(message("/run rassegna", user=USER_ID)))

    to_requester = [text for chat_id, text in app.gateway.sent if chat_id == USER_ID]
    assert any("Esecuzione non riuscita" in text for text in to_requester)
    stored = app.repos.executions.list()
    assert [row.outcome for row in stored] == ["errore"]
    app.db.close()
