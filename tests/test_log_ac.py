"""AC-01…AC-03 di spec 07, end-to-end sull'applicazione con dipendenze finte."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from agente.app import AgentApp
from agente.device import DeviceAdapter
from agente.llm import LLMResponse, ToolCall
from agente.storage.repositories import Task, User
from conftest import ADMIN_ID, USER_ID
from test_scheduled_ac import AppScheduler

NOW = datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc)


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


class LogLLM:
    """Prima risposta con `read_logs`, poi il riassunto finale."""

    def __init__(self, path: str, answer: str = "Riassunto dei log.") -> None:
        self.path = path
        self.answer = answer
        self.calls: list[list[dict]] = []

    def chat(self, messages, tools=None):
        self.calls.append([dict(item) for item in messages])
        if len(self.calls) == 1:
            return LLMResponse(
                text="",
                tool_calls=(
                    ToolCall(id="1", name="read_logs", arguments={"path": self.path}),
                ),
            )
        return LLMResponse(text=self.answer)

    def summarize(self, text: str) -> str:
        return text

    def tool_output(self) -> str:
        return "\n".join(
            message.get("content", "")
            for message in self.calls[-1]
            if message.get("role") == "tool"
        )


def build_app(make_config, llm) -> AgentApp:
    config = make_config(admin_id=ADMIN_ID)
    gateway = Gateway()
    app = AgentApp.build(
        config,
        gateway=gateway,
        scheduler=AppScheduler(),
        llm=llm,
        device=DeviceAdapter(),
        clock=lambda: NOW,
    )
    app.db.migrate()
    app.repos.users.upsert(
        User(telegram_id=USER_ID, username="utente", state="accepted")
    )
    return app


def make_task(app, *paths: str) -> Task:
    return app.repos.tasks.create(
        Task(
            name="log",
            instructions="riassumi i log e indica gli errori",
            schedule_type="orario",
            schedule_expr="08:00",
            created_by=ADMIN_ID,
            log_allowlist=list(paths),
        )
    )


def test_ac01_authorized_folder_is_summarized_with_errors(
    make_config, tmp_path: Path
) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "app.log").write_text(
        "2026-10-29 08:00 INFO avvio\n2026-10-29 08:01 ERROR connessione persa\n",
        encoding="utf-8",
    )
    (logs / "access.log").write_text("2026-10-29 08:02 INFO richiesta ok\n", encoding="utf-8")
    llm = LogLLM(str(logs), answer="Un errore: connessione persa.")
    app = build_app(make_config, llm)
    task = make_task(app, str(logs))

    result = asyncio.run(app.execution.execute(task, "manual", requester=ADMIN_ID))

    assert result.outcome == "ok"
    assert "ERROR connessione persa" in llm.tool_output()
    assert "INFO richiesta ok" in llm.tool_output()
    assert result.text == "Un errore: connessione persa."
    assert app.gateway.last() == "Un errore: connessione persa."
    app.db.close()


def test_ac02_unauthorized_path_is_refused_and_admin_is_alerted(
    make_config, tmp_path: Path
) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "app.log").write_text("INFO ok\n", encoding="utf-8")
    secret = tmp_path / "segreto.txt"
    secret.write_text("contenuto riservato", encoding="utf-8")
    llm = LogLLM(str(secret), answer="Non posso leggere quel file.")
    app = build_app(make_config, llm)
    task = make_task(app, str(logs))

    result = asyncio.run(app.execution.execute(task, "manual", requester=ADMIN_ID))

    assert result.outcome == "ok"
    assert "PERCORSO NON AUTORIZZATO" in llm.tool_output()
    assert all("contenuto riservato" not in str(call) for call in llm.calls)
    assert any(
        f"Log non autorizzati per il compito {task.name}: {secret}" in text
        for text in app.gateway.texts()
    )
    assert result.text.startswith(f"Log non autorizzati: {secret}")
    assert result.text.endswith("Non posso leggere quel file.")
    app.db.close()


def test_ac03_agent_logs_are_summarized(make_config, tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "agente.jsonl").write_text(
        "\n".join(
            [
                '{"ts": "2026-10-29T08:00:00+0100", "level": "INFO", '
                '"message": "esecuzione conclusa", "task_id": 3, "outcome": "ok"}',
                '{"ts": "2026-10-29T08:05:00+0100", "level": "ERROR", '
                '"message": "esecuzione fallita", "task_id": 4, '
                '"error": "LLMError"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    llm = LogLLM(str(logs), answer="Un'esecuzione ok, una fallita per LLMError.")
    app = build_app(make_config, llm)
    task = make_task(app, str(logs))

    result = asyncio.run(app.execution.execute(task, "manual", requester=ADMIN_ID))

    assert result.outcome == "ok"
    assert "esecuzione conclusa" in llm.tool_output()
    assert "esecuzione fallita" in llm.tool_output()
    assert "LLMError" in llm.tool_output()
    assert app.gateway.last() == "Un'esecuzione ok, una fallita per LLMError."
    app.db.close()
