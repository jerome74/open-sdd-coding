"""AC-01…AC-03 di spec 06 e AC-06 di spec 05, end-to-end sull'app."""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
from datetime import datetime, timezone

from agente.app import AgentApp
from agente.config import SearchConfig
from agente.device import DeviceAdapter
from agente.llm import LLMResponse, ToolCall
from agente.storage.repositories import Task, User
from agente.telegram_gateway import IncomingMessage
from agente.web_search import Result
from conftest import ADMIN_ID, USER_ID
from test_scheduled_ac import AppScheduler

NOW = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)


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

    def last(self) -> str:
        return self.sent[-1][1]


class Runner:
    def __call__(self, cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"supplicant_state": "COMPLETED"}), stderr=""
        )


class ToolThenTextLLM:
    def __init__(self, tool: str, arguments: dict, text: str = "fatto") -> None:
        self.tool = tool
        self.arguments = arguments
        self.text = text
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                text="",
                tool_calls=(
                    ToolCall(id="1", name=self.tool, arguments=self.arguments),
                ),
            )
        return LLMResponse(text=self.text)

    def summarize(self, text: str) -> str:
        return text


class FakeSearch:
    def __init__(self, *, delay: float = 0.0) -> None:
        self.delay = delay
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, k: int):
        self.calls.append((query, k))
        if self.delay:
            time.sleep(self.delay)
        return [Result("Meteo", "https://example.test/meteo", "Sereno")]


def build_app(make_config, llm, *, search=None, **limits):
    config = make_config(
        admin_id=ADMIN_ID,
        search=SearchConfig(provider="tavily", api_key="test-key"),
        **limits,
    )
    gateway = Gateway()
    app = AgentApp.build(
        config,
        gateway=gateway,
        scheduler=AppScheduler(),
        llm=llm,
        device=DeviceAdapter(runner=Runner()),
        search=search,
        clock=lambda: NOW,
    )
    app.db.migrate()
    app.repos.users.upsert(
        User(telegram_id=USER_ID, username="utente", state="accepted")
    )
    return app


def make_task(app) -> Task:
    return app.repos.tasks.create(
        Task(
            name="pulizia",
            instructions="cancella il file temporaneo",
            schedule_type="orario",
            schedule_expr="08:00",
            created_by=ADMIN_ID,
        )
    )


def pending_approval(app) -> int | None:
    rows = app.repos.approvals._conn.execute(
        "SELECT id FROM approvals WHERE status = 'pending'"
    ).fetchall()
    return int(rows[0]["id"]) if rows else None


async def wait_for_approval(app):
    for _ in range(300):
        approval_id = pending_approval(app)
        if approval_id is not None:
            return approval_id
        await asyncio.sleep(0.01)
    raise AssertionError("richiesta di approvazione non creata")


def test_ac01_file_is_not_touched_before_approval(make_config, tmp_path) -> None:
    target = tmp_path / "da-cancellare.txt"
    target.write_text("contenuto", encoding="utf-8")
    llm = ToolThenTextLLM("delete_file", {"path": str(target)})
    app = build_app(make_config, llm)
    task = make_task(app)

    async def scenario() -> None:
        execution = asyncio.create_task(
            app.execution.execute(task, "manual", requester=ADMIN_ID)
        )
        await wait_for_approval(app)
        assert target.exists(), "il file non deve essere toccato prima dell'approvazione"
        execution.cancel()
        try:
            await execution
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())
    app.db.close()

    # Il file esiste ancora e il modello non ha ricevuto una seconda chiamata.
    assert target.exists()
    assert llm.calls == 1


def test_ac01_file_is_deleted_after_approval(make_config, tmp_path) -> None:
    target = tmp_path / "da-cancellare.txt"
    target.write_text("contenuto", encoding="utf-8")
    llm = ToolThenTextLLM("delete_file", {"path": str(target)})
    app = build_app(make_config, llm)
    task = make_task(app)

    async def scenario():
        execution = asyncio.create_task(
            app.execution.execute(task, "manual", requester=ADMIN_ID)
        )
        approval_id = await wait_for_approval(app)
        action = await app.router.route(
            IncomingMessage(
                user_id=ADMIN_ID,
                chat_id=ADMIN_ID,
                callback_data=f"approval:{approval_id}:approve",
            )
        )
        assert action.kind == "approval_resolved"
        return await execution

    result = asyncio.run(scenario())

    assert result.outcome == "ok"
    assert not target.exists()
    assert "Azione approvata." in app.gateway.texts()
    app.db.close()


def test_ac02_unanswered_request_is_rejected(make_config, tmp_path) -> None:
    target = tmp_path / "da-cancellare.txt"
    target.write_text("contenuto", encoding="utf-8")
    llm = ToolThenTextLLM("delete_file", {"path": str(target)}, text="non posso")
    app = build_app(make_config, llm, approval_timeout_s=1)
    task = make_task(app)

    async def scenario():
        return await app.execution.execute(task, "manual", requester=ADMIN_ID)

    result = asyncio.run(scenario())

    assert result.outcome == "ok"
    assert target.exists(), "l'azione rifiutata non deve essere eseguita"
    rows = app.repos.approvals._conn.execute(
        "SELECT status FROM approvals"
    ).fetchall()
    assert [row["status"] for row in rows] == ["rejected"]
    app.db.close()


def test_ac03_web_search_needs_no_confirmation(make_config) -> None:
    search = FakeSearch()
    llm = ToolThenTextLLM("web_search", {"query": "meteo"}, text="Sereno a Roma")
    app = build_app(make_config, llm, search=search)

    async def scenario():
        return await app.chat.handle(USER_ID, USER_ID, "che tempo fa?")

    reply = asyncio.run(scenario())

    assert reply.kind == "answered"
    assert search.calls == [("meteo", 5)]
    assert "Richiesta di conferma" not in "\n".join(app.gateway.texts())
    assert app.repos.approvals._conn.execute(
        "SELECT COUNT(*) AS n FROM approvals"
    ).fetchone()["n"] == 0
    assert app.gateway.last() == "Sereno a Roma"
    app.db.close()


def test_ac06_web_search_closes_the_gap(make_config) -> None:
    search = FakeSearch(delay=1.05)
    llm = ToolThenTextLLM("web_search", {"query": "meteo"}, text="Sereno a Roma")
    app = build_app(make_config, llm, search=search, chat_progress_s=1)

    async def scenario():
        return await app.chat.handle(USER_ID, USER_ID, "che tempo fa?")

    reply = asyncio.run(scenario())

    assert reply.kind == "answered"
    assert "sto cercando…" in app.gateway.texts()
    assert app.gateway.deleted, "l'indicatore deve essere eliminato alla risposta"
    assert app.gateway.last() == "Sereno a Roma"
    assert "Richiesta di conferma" not in "\n".join(app.gateway.texts())
    app.db.close()
