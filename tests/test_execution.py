"""C-09: esecuzione, lock per compito, timeout, esito registrato."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agente.delivery import DeliveryReport
from agente.errors import LLMError, LockHeldError, LogAccessError, SearchError
from agente.execution import ExecutionEngine
from agente.gate import ActionGate
from agente.history import HistoryService
from agente.llm import LLMResponse, ToolCall
from agente.storage.db import Database
from agente.storage.repositories import Approval, Task, repositories
from agente.tools import Tool, ToolRegistry

NOW = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)


class FakeLLM:
    def __init__(self, *, delay: float = 0.0, error: Exception | None = None) -> None:
        self.delay = delay
        self.error = error

    def chat(self, messages, tools=None):
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return LLMResponse(text="risultato")


class FakeNotifications:
    def __init__(self) -> None:
        self.alerts: list[str] = []

    async def alert_admin(self, text: str) -> None:
        self.alerts.append(text)

    async def notify(self, recipients, text: str) -> None:
        return None


class FakeDelivery:
    def __init__(self, fail: tuple[int, ...] = ()) -> None:
        self.fail = fail
        self.delivered: list[tuple[int, str]] = []
        self.recipients_seen: list[int | None] = []

    async def deliver(self, task, result, *, requested_by=None):
        return await self.deliver_text(task, result.text, requested_by=requested_by)

    async def deliver_text(self, task, text: str, *, requested_by=None):
        self.delivered.append((task.id, text))
        self.recipients_seen.append(requested_by)
        if self.fail:
            return DeliveryReport(failed=self.fail)
        return DeliveryReport(sent=(requested_by or 1,))


@pytest.fixture
def env(tmp_path: Path):
    db = Database(tmp_path / "e.db")
    db.migrate()
    repos = repositories(db.connection)
    task = repos.tasks.create(
        Task(name="t", instructions="i", schedule_type="orario", schedule_expr="08:00", created_by=1)
    )
    history = HistoryService(
        repos.executions,
        repos.conversations,
        retention_days=30,
        chat_memory_hours=24,
        clock=lambda: NOW,
    )
    yield repos, history, task
    db.close()


def test_successful_execution_is_recorded(env) -> None:
    repos, history, task = env
    notifications = FakeNotifications()
    engine = ExecutionEngine(FakeLLM(), history, notifications, timeout_s=10)

    result = asyncio.run(engine.execute(task, "manual", requester=2))

    assert result.outcome == "ok"
    assert result.summary == "risultato"
    stored = repos.executions.list()
    assert stored[0].outcome == "ok"
    assert stored[0].trigger == "manual"
    assert notifications.alerts == []


def test_timeout_marks_interrupted_and_alerts_admin(env) -> None:
    repos, history, task = env
    notifications = FakeNotifications()
    engine = ExecutionEngine(FakeLLM(delay=0.3), history, notifications, timeout_s=0.05)

    result = asyncio.run(engine.execute(task, "scheduled"))

    assert result.outcome == "interrotto"
    assert repos.executions.list()[0].outcome == "interrotto"
    assert len(notifications.alerts) == 1


def test_llm_error_marks_failed(env) -> None:
    repos, history, task = env
    notifications = FakeNotifications()
    engine = ExecutionEngine(
        FakeLLM(error=LLMError("boom")), history, notifications, timeout_s=10
    )

    result = asyncio.run(engine.execute(task, "manual"))

    assert result.outcome == "errore"
    assert "LLMError" in (result.summary or "")
    assert repos.executions.list()[0].outcome == "errore"
    assert len(notifications.alerts) == 1


def test_one_execution_per_task_at_a_time(env) -> None:
    repos, history, task = env
    engine = ExecutionEngine(FakeLLM(delay=0.2), history, FakeNotifications(), timeout_s=10)

    async def scenario():
        return await asyncio.gather(
            engine.execute(task, "manual"),
            engine.execute(task, "manual"),
            return_exceptions=True,
        )

    results = asyncio.run(scenario())
    outcomes = [result for result in results if isinstance(result, Exception)]
    assert len(outcomes) == 1
    assert isinstance(outcomes[0], LockHeldError)
    assert len(repos.executions.list()) == 1


def test_invalid_trigger_is_rejected(env) -> None:
    _repos, history, task = env
    engine = ExecutionEngine(FakeLLM(), history, FakeNotifications(), timeout_s=10)
    with pytest.raises(ValueError):
        asyncio.run(engine.execute(task, "boh"))


def test_read_only_tool_is_executed_and_result_is_delivered(env) -> None:
    _repos, history, task = env
    registry = ToolRegistry()
    invoked: list[tuple[int, dict]] = []

    def handler(task, arguments):
        invoked.append((task.id, arguments))
        return "contenuto del log"

    registry.register(
        Tool(
            name="read_logs",
            description="legge un log",
            read_only=True,
            requires_approval=False,
            handler=handler,
        )
    )
    delivery = FakeDelivery()
    engine = ExecutionEngine(
        ToolLLM(),
        history,
        FakeNotifications(),
        timeout_s=10,
        tools=registry,
        delivery=delivery,
    )

    result = asyncio.run(engine.execute(task, "scheduled"))

    assert result.outcome == "ok"
    assert result.text == "esito con log"
    assert invoked == [(task.id, {"path": "/tmp/log"})]
    assert delivery.delivered == [(task.id, "esito con log")]


def test_modifying_tool_is_refused_fail_safe(env) -> None:
    _repos, history, task = env
    registry = ToolRegistry()
    executed: list[str] = []

    def handler(task, arguments):
        executed.append("eseguito")
        return "no"

    registry.register(
        Tool(
            name="run_command",
            description="comando",
            read_only=False,
            requires_approval=True,
            handler=handler,
        )
    )
    notifications = FakeNotifications()
    engine = ExecutionEngine(
        ToolLLM(name="run_command"),
        history,
        notifications,
        timeout_s=10,
        tools=registry,
    )

    result = asyncio.run(engine.execute(task, "scheduled"))

    assert result.outcome == "errore"
    assert executed == []
    assert len(notifications.alerts) == 1


def test_delivery_failure_marks_error(env) -> None:
    repos, history, task = env
    notifications = FakeNotifications()
    engine = ExecutionEngine(
        FakeLLM(),
        history,
        notifications,
        timeout_s=10,
        delivery=FakeDelivery(fail=(2,)),
    )

    result = asyncio.run(engine.execute(task, "scheduled"))

    assert result.outcome == "errore"
    assert "consegna fallita" in (result.summary or "")
    assert repos.executions.list()[0].outcome == "errore"
    assert len(notifications.alerts) == 1


class ToolLLM:
    """Prima risposta con tool call, poi il risultato finale."""

    def __init__(self, name: str = "read_logs") -> None:
        self.name = name
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                text="",
                tool_calls=(
                    ToolCall(id="c1", name=self.name, arguments={"path": "/tmp/log"}),
                ),
            )
        return LLMResponse(text="esito con log")


def test_manual_timeout_is_interrupted(env) -> None:
    _repos, history, task = env
    notifications = FakeNotifications()
    engine = ExecutionEngine(
        FakeLLM(delay=0.3), history, notifications, timeout_s=0.05
    )

    result = asyncio.run(engine.execute(task, "manual", requester=2))

    assert result.outcome == "interrotto"
    assert len(notifications.alerts) == 1
    assert engine.is_running(task.id) is False


def test_manual_result_is_delivered_only_to_the_requester(env) -> None:
    _repos, history, task = env
    delivery = FakeDelivery()
    engine = ExecutionEngine(
        FakeLLM(), history, FakeNotifications(), timeout_s=10, delivery=delivery
    )

    asyncio.run(engine.execute(task, "manual", requester=2))

    assert delivery.delivered == [(task.id, "risultato")]
    assert delivery.recipients_seen == [2]


def test_scheduled_result_keeps_the_default_recipients(env) -> None:
    _repos, history, task = env
    delivery = FakeDelivery()
    engine = ExecutionEngine(
        FakeLLM(), history, FakeNotifications(), timeout_s=10, delivery=delivery
    )

    asyncio.run(engine.execute(task, "scheduled"))

    assert delivery.recipients_seen == [None]


def test_lock_is_released_after_an_error(env) -> None:
    _repos, history, task = env
    engine = ExecutionEngine(
        FakeLLM(error=LLMError("boom")), history, FakeNotifications(), timeout_s=10
    )

    asyncio.run(engine.execute(task, "manual", requester=2))

    assert engine.is_running(task.id) is False


class FakeApprovals:
    def __init__(self, status: str = "approved") -> None:
        self.status = status
        self.requests: list[dict] = []

    async def request(self, **kwargs):
        self.requests.append(kwargs)
        return Approval(
            action=kwargs["action"],
            reason=kwargs["reason"],
            expires_at="2099-01-01T00:00:00+00:00",
            status=self.status,
        )

    def is_executable(self, approval: Approval) -> bool:
        return approval.status == "approved"


class BlockingApprovals:
    def __init__(self) -> None:
        self.cancelled = False

    async def request(self, **kwargs):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    def is_executable(self, approval: Approval) -> bool:
        return False


def test_rejected_approval_lets_the_execution_continue(env) -> None:
    _repos, history, task = env
    executed: list[str] = []
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="delete_file",
            description="cancella",
            read_only=False,
            requires_approval=True,
            handler=lambda task, arguments, approved=False: executed.append("run")
            or "cancellato",
        )
    )
    approvals = FakeApprovals("rejected")
    gate = ActionGate(registry, approvals)
    delivery = FakeDelivery()
    engine = ExecutionEngine(
        ToolLLM(name="delete_file"),
        history,
        FakeNotifications(),
        timeout_s=10,
        tools=registry,
        delivery=delivery,
        gate=gate,
    )

    result = asyncio.run(engine.execute(task, "scheduled"))

    assert result.outcome == "ok"
    assert executed == []
    assert approvals.requests
    assert delivery.delivered == [(task.id, "esito con log")]


def test_search_error_is_a_tool_outcome(env) -> None:
    _repos, history, task = env
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="web_search",
            description="cerca",
            read_only=True,
            requires_approval=False,
            handler=lambda task, arguments: (_ for _ in ()).throw(
                SearchError("ricerca web non configurata")
            ),
        )
    )
    gate = ActionGate(registry, FakeApprovals())
    delivery = FakeDelivery()
    engine = ExecutionEngine(
        ToolLLM(name="web_search"),
        history,
        FakeNotifications(),
        timeout_s=10,
        tools=registry,
        delivery=delivery,
        gate=gate,
    )

    result = asyncio.run(engine.execute(task, "scheduled"))

    assert result.outcome == "ok"
    assert delivery.delivered == [(task.id, "esito con log")]


def test_pending_approval_is_rejected_when_execution_times_out(env) -> None:
    _repos, history, task = env
    executed: list[str] = []
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="delete_file",
            description="cancella",
            read_only=False,
            requires_approval=True,
            handler=lambda task, arguments, approved=False: executed.append("run")
            or "cancellato",
        )
    )
    approvals = BlockingApprovals()
    gate = ActionGate(registry, approvals)
    notifications = FakeNotifications()
    engine = ExecutionEngine(
        ToolLLM(name="delete_file"),
        history,
        notifications,
        timeout_s=0.1,
        tools=registry,
        gate=gate,
    )

    result = asyncio.run(engine.execute(task, "scheduled"))

    assert result.outcome == "interrotto"
    assert executed == []
    assert approvals.cancelled is True
    assert notifications.alerts


def _refusing_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="read_logs",
            description="legge",
            read_only=True,
            requires_approval=False,
            handler=lambda task, arguments: (_ for _ in ()).throw(
                LogAccessError(
                    "Percorsi non autorizzati: /etc/shadow",
                    refused=("/etc/shadow",),
                    rendered="== PERCORSO NON AUTORIZZATO: /etc/shadow ==",
                )
            ),
        )
    )
    return registry


def test_log_access_error_alerts_admin_and_execution_continues(env) -> None:
    _repos, history, task = env
    registry = _refusing_registry()
    gate = ActionGate(registry, FakeApprovals())
    delivery = FakeDelivery()
    notifications = FakeNotifications()
    engine = ExecutionEngine(
        ToolLLM(),
        history,
        notifications,
        timeout_s=10,
        tools=registry,
        delivery=delivery,
        gate=gate,
    )

    result = asyncio.run(engine.execute(task, "scheduled"))

    assert result.outcome == "ok"
    assert notifications.alerts == [
        f"Log non autorizzati per il compito {task.name}: /etc/shadow"
    ]
    assert delivery.delivered == [
        (task.id, "Log non autorizzati: /etc/shadow\nesito con log")
    ]


def test_log_access_error_note_is_delivered(env) -> None:
    _repos, history, task = env
    registry = _refusing_registry()
    delivery = FakeDelivery()
    engine = ExecutionEngine(
        ToolLLM(),
        history,
        FakeNotifications(),
        timeout_s=10,
        tools=registry,
        delivery=delivery,
    )

    result = asyncio.run(engine.execute(task, "scheduled"))

    assert result.outcome == "ok"
    assert result.text.startswith("Log non autorizzati: /etc/shadow")
    assert delivery.delivered[0][1] == result.text


class FakeAlerts:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    async def alert(self, kind: str, detail: dict) -> bool:
        self.sent.append((kind, detail))
        return True


def test_timeout_uses_alert_service(env) -> None:
    _repos, history, task = env
    alerts = FakeAlerts()
    engine = ExecutionEngine(
        FakeLLM(delay=0.3),
        history,
        FakeNotifications(),
        timeout_s=0.05,
        alerts=alerts,  # type: ignore[arg-type]
    )

    asyncio.run(engine.execute(task, "scheduled"))

    assert alerts.sent[0][0] == "task_timeout"
    assert alerts.sent[0][1]["task"] == task.name


def test_generic_failure_uses_alert_service(env) -> None:
    _repos, history, task = env
    alerts = FakeAlerts()
    engine = ExecutionEngine(
        FakeLLM(error=LLMError("boom")),
        history,
        FakeNotifications(),
        timeout_s=10,
        alerts=alerts,  # type: ignore[arg-type]
    )

    asyncio.run(engine.execute(task, "manual"))

    assert alerts.sent == [("task_failed", {"task": task.name, "reason": "LLMError"})]


def test_credential_error_does_not_alert_task_failed(env) -> None:
    from agente.errors import LLMCredentialsError

    _repos, history, task = env
    alerts = FakeAlerts()
    engine = ExecutionEngine(
        FakeLLM(error=LLMCredentialsError("no credit", status=402)),
        history,
        FakeNotifications(),
        timeout_s=10,
        alerts=alerts,  # type: ignore[arg-type]
    )

    result = asyncio.run(engine.execute(task, "manual"))

    assert result.outcome == "errore"
    assert alerts.sent == []
