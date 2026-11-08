"""AC-01…AC-03 di spec 09, end-to-end sull'applicazione con dipendenze finte."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from agente.app import AgentApp
from agente.llm import LLMResponse
from agente.storage.repositories import Task, User
from agente.telegram_gateway import IncomingMessage
from conftest import ADMIN_ID, USER_ID
from test_scheduled_ac import AppScheduler

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


class Gateway:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []
        self._next_id = 0

    async def send(self, chat_id, text, keyboard=None) -> int:
        self._next_id += 1
        self.sent.append((chat_id, text, keyboard))
        return self._next_id

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        return None

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


def message(text: str = "", *, user: int) -> IncomingMessage:
    return IncomingMessage(user_id=user, chat_id=user, text=text)


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


def _task(app: AgentApp, name: str) -> Task:
    return app.repos.tasks.create(
        Task(
            name=name,
            instructions="riassumi",
            schedule_type="orario",
            schedule_expr="08:00",
            created_by=ADMIN_ID,
        )
    )


def _execution(app: AgentApp, task: Task, *, at: datetime, outcome="ok", summary="fatto"):
    execution = app.history.record(
        task_id=task.id,
        trigger="scheduled",
        requested_by=None,
        started_at=at.isoformat(timespec="seconds"),
    )
    app.history.finish(execution.id, outcome=outcome, summary=summary)
    return execution


def test_ac01_admin_asks_about_yesterday(app: AgentApp) -> None:
    task = _task(app, "news")
    _execution(app, task, at=NOW - timedelta(days=1))

    action = asyncio.run(
        app.router.route(message("cosa hai fatto ieri?", user=ADMIN_ID))
    )

    assert action.kind == "history"
    text = app.gateway.last()
    assert text.startswith("Storico — ieri (31/10)")
    assert "news — ok — fatto" in text


def test_ac02_authorized_user_sees_only_subscribed_tasks(app: AgentApp) -> None:
    app.repos.users.upsert(
        User(telegram_id=USER_ID, username="utente", state="accepted")
    )
    news = _task(app, "news")
    log = _task(app, "log")
    app.repos.subscriptions.add(USER_ID, news.id)
    _execution(app, news, at=NOW - timedelta(hours=2))
    _execution(app, log, at=NOW - timedelta(hours=1))

    action = asyncio.run(app.router.route(message("/history", user=USER_ID)))

    assert action.kind == "history"
    text = app.gateway.last()
    assert "news" in text
    assert "log" not in text


def test_ac03_expired_execution_is_not_listed(app: AgentApp) -> None:
    task = _task(app, "news")
    _execution(app, task, at=NOW - timedelta(days=31), summary="vecchia")
    _execution(app, task, at=NOW - timedelta(days=2), summary="recente")

    stats = app.history.purge_expired()
    assert stats.executions_deleted == 1

    action = asyncio.run(app.router.route(message("/history 30g", user=ADMIN_ID)))

    assert action.kind == "history"
    text = app.gateway.last()
    assert "recente" in text
    assert "vecchia" not in text
