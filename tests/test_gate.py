"""C-27: classificazione, conferma, fail-safe ed esecuzione (spec 06)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import pytest

from agente.errors import DeviceError, GateError, SearchError
from agente.gate import ActionGate, ToolAction
from agente.storage.repositories import Approval
from agente.tools import Tool, ToolRegistry

APPROVED = "approved"
REJECTED = "rejected"


def _approval(status: str = APPROVED) -> Approval:
    return Approval(
        action="azione",
        reason="motivo",
        expires_at="2099-01-01T00:00:00+00:00",
        status=status,
    )


class FakeApprovals:
    def __init__(self, status: str = APPROVED, *, executable: bool = True) -> None:
        self.status = status
        self.executable = executable
        self.requests: list[dict] = []

    async def request(self, **kwargs):
        self.requests.append(kwargs)
        return _approval(self.status)

    def is_executable(self, approval: Approval) -> bool:
        return self.status == APPROVED and self.executable


class BlockingApprovals(FakeApprovals):
    def __init__(self) -> None:
        super().__init__()
        self.release = asyncio.Event()
        self.started = asyncio.Event()

    async def request(self, **kwargs):
        self.started.set()
        await self.release.wait()
        return await super().request(**kwargs)


def registry(*, search=None) -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(
        Tool(
            name="read_logs",
            description="legge",
            read_only=True,
            requires_approval=False,
            handler=lambda context, arguments: "contenuto",
        )
    )
    tools.register(
        Tool(
            name="delete_file",
            description="cancella",
            read_only=False,
            requires_approval=True,
            handler=lambda context, arguments, approved=False: (
                f"cancellato approved={approved}"
            ),
        )
    )
    return tools


def action(name: str = "delete_file") -> ToolAction:
    return ToolAction(
        tool=name,
        arguments={"path": "/tmp/x"},
        context=object(),
        reason="pulizia",
        requested_by=2,
    )


def test_read_only_action_is_executed_without_approval() -> None:
    approvals = FakeApprovals()
    gate = ActionGate(registry(), approvals)

    assert gate.classify(action("read_logs")).kind == "read_only"
    assert asyncio.run(gate.run(action("read_logs"))) == "contenuto"
    assert approvals.requests == []


def test_modifying_action_requires_an_approval() -> None:
    approvals = FakeApprovals()
    gate = ActionGate(registry(), approvals)

    assert gate.classify(action()).kind == "modifying"
    result = asyncio.run(gate.run(action()))

    assert result == "cancellato approved=True"
    assert approvals.requests[0]["action"].startswith("delete_file")
    assert approvals.requests[0]["reason"] == "pulizia"
    assert approvals.requests[0]["requester"] == 2


def test_modifying_action_without_approval_is_refused() -> None:
    gate = ActionGate(registry(), FakeApprovals())

    with pytest.raises(GateError, match="approvazione"):
        gate.execute_if_allowed(action(), None)


def test_rejected_approval_is_not_executed() -> None:
    approval = _approval(REJECTED)
    gate = ActionGate(registry(), FakeApprovals(REJECTED))

    with pytest.raises(GateError):
        gate.execute_if_allowed(action(), approval)
    assert asyncio.run(gate.run(action())) == (
        "azione non eseguita: approvazione dell'amministratore non concessa."
    )


def test_expired_approval_is_not_executable() -> None:
    gate = ActionGate(registry(), FakeApprovals(executable=False))

    assert asyncio.run(gate.run(action())) == (
        "azione non eseguita: approvazione dell'amministratore non concessa."
    )


def test_unknown_tool_is_never_executed() -> None:
    approvals = FakeApprovals()
    gate = ActionGate(registry(), approvals)

    assert gate.classify(action("sconosciuto")).kind == "unknown"
    assert asyncio.run(gate.run(action("sconosciuto"))) == (
        "strumento non disponibile: sconosciuto"
    )
    assert approvals.requests == []


def test_modifying_handler_runs_only_after_approval() -> None:
    called: list[str] = []
    tools = ToolRegistry()
    tools.register(
        Tool(
            name="delete_file",
            description="cancella",
            read_only=False,
            requires_approval=True,
            handler=lambda context, arguments, approved=False: called.append("run")
            or "ok",
        )
    )
    approvals = BlockingApprovals()
    gate = ActionGate(tools, approvals)

    async def scenario() -> str:
        pending = asyncio.create_task(gate.run(action()))
        await approvals.started.wait()
        assert called == []
        approvals.release.set()
        return await pending

    assert asyncio.run(scenario()) == "ok"
    assert called == ["run"]


def test_search_error_is_a_tool_outcome() -> None:
    tools = ToolRegistry()
    tools.register(
        Tool(
            name="web_search",
            description="cerca",
            read_only=True,
            requires_approval=False,
            handler=lambda context, arguments: (_ for _ in ()).throw(
                SearchError("ricerca web non configurata")
            ),
        )
    )
    gate = ActionGate(tools, FakeApprovals())

    result = asyncio.run(gate.run(action("web_search")))

    assert "errore dello strumento" in result
    assert "non configurata" in result


def test_device_error_propagates() -> None:
    tools = ToolRegistry()
    tools.register(
        Tool(
            name="read_logs",
            description="legge",
            read_only=True,
            requires_approval=False,
            handler=lambda context, arguments: (_ for _ in ()).throw(
                DeviceError("file assente")
            ),
        )
    )
    gate = ActionGate(tools, FakeApprovals())

    with pytest.raises(DeviceError):
        asyncio.run(gate.run(action("read_logs")))


def test_gate_logs_the_decision(caplog) -> None:
    gate = ActionGate(registry(), FakeApprovals())

    with caplog.at_level(logging.INFO, logger="agente.gate"):
        asyncio.run(gate.run(action()))

    messages = [record.message for record in caplog.records]
    assert "gate: classificazione" in messages
    assert "gate: esecuzione approvata" in messages


def test_execute_if_allowed_refuses_an_expired_approval() -> None:
    gate = ActionGate(
        registry(),
        FakeApprovals(),
        clock=lambda: datetime(2100, 1, 1, tzinfo=timezone.utc),
    )
    approval = _approval()

    with pytest.raises(GateError):
        gate.execute_if_allowed(action(), approval)
