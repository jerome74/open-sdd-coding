"""AC-01: avvio senza intervento manuale con componenti esterni finti."""

from __future__ import annotations

import asyncio

import pytest
from datetime import datetime, timezone
from pathlib import Path

from agente.app import AgentApp
from agente.llm import LLMResponse
from agente.storage.repositories import Approval


class FakeGateway:
    def __init__(self, *, fail_start: bool = False) -> None:
        self.started = False
        self.stopped = False
        self.handlers: list[object] = []
        self.sent: list[tuple[int, str]] = []
        self.fail_start = fail_start

    def add_handler(self, handler, group: int = 0) -> None:
        self.handlers.append(handler)

    def set_inbound_handler(self, handler) -> None:
        self.inbound = handler

    async def start(self) -> None:
        if self.fail_start:
            raise OSError("rete assente")
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send(self, chat_id, text, keyboard=None) -> None:
        self.sent.append((chat_id, text))


class FakeScheduler:
    def __init__(self) -> None:
        self.started = False
        self.paused = False
        self.resumed = False
        self.stopped = False
        self.maintenance = None
        self.connectivity = None
        self.battery = None
        self.liveness = None
        self.dispatcher = None

    def set_dispatcher(self, dispatcher) -> None:
        self.dispatcher = dispatcher

    def schedule_task(self, task, trigger) -> str:
        return f"task:{task.id}"

    def unschedule_task(self, task_id: int) -> None:
        return None

    def next_run(self, task_id: int):
        return None

    def start(self, *, paused: bool = False) -> None:
        self.started = True
        self.paused = paused

    def resume(self) -> None:
        self.resumed = True

    def shutdown(self, wait: bool = False) -> None:
        self.stopped = True

    def schedule_maintenance(self, callback, *, interval_hours: int = 24) -> str:
        self.maintenance = callback
        return "maintenance:purge"

    def schedule_connectivity(self, callback, *, interval_s: int = 60) -> str:
        self.connectivity = callback
        return "connectivity:check"

    def schedule_battery(self, callback, *, interval_s: int = 300) -> str:
        self.battery = callback
        self.battery_interval_s = interval_s
        return "battery:check"

    def schedule_liveness(self, callback, *, at: str = "08:00") -> str:
        self.liveness = callback
        self.liveness_at = at
        return "liveness:send"


class FakeDevice:
    def __init__(self, online: bool = True) -> None:
        self.online = online

    def is_online(self) -> bool:
        return self.online

    def record_last_contact(self, settings, when=None) -> str:
        moment = (when or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        settings.set("last_contact_at", moment)
        return moment


class FakeLLM:
    def chat(self, messages, tools=None):
        return LLMResponse(text="ok")


def test_start_migrates_starts_polling_and_scheduler(make_config, tmp_path: Path) -> None:
    config = make_config()
    gateway = FakeGateway()
    scheduler = FakeScheduler()
    app = AgentApp.build(
        config, gateway=gateway, scheduler=scheduler, llm=FakeLLM(), device=FakeDevice()
    )

    asyncio.run(app.start())
    try:
        assert gateway.started is True
        assert scheduler.started is True
        assert scheduler.paused is True
        assert scheduler.resumed is True
        assert scheduler.maintenance is not None
        assert scheduler.connectivity is not None
        tables = {
            row["name"]
            for row in app.db.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"tasks", "users", "executions", "settings"} <= tables
        assert app.db.schema_version() == "005_executions_started_index"
    finally:
        asyncio.run(app.stop())

    assert gateway.stopped is True
    assert scheduler.stopped is True


def test_start_registers_handlers(make_config) -> None:
    config = make_config()
    gateway = FakeGateway()
    app = AgentApp.build(
        config,
        gateway=gateway,
        scheduler=FakeScheduler(),
        llm=FakeLLM(),
        device=FakeDevice(),
    )
    asyncio.run(app.start([object()]))
    try:
        assert len(gateway.handlers) == 1
        assert gateway.inbound == app.router.route
        assert app.scheduler.dispatcher is not None
    finally:
        asyncio.run(app.stop())


def test_dispatch_skips_missing_or_paused_tasks(make_config) -> None:
    config = make_config()
    app = AgentApp.build(
        config,
        gateway=FakeGateway(),
        scheduler=FakeScheduler(),
        llm=FakeLLM(),
        device=FakeDevice(),
    )
    app.db.migrate()
    from agente.schedule_interpreter import Schedule
    from agente.task_manager import TaskDraft

    task = app.tasks.create(
        TaskDraft(name="rassegna", instructions="x", schedule=Schedule("orario", "08:00"))
    )
    app.tasks.pause(task.id)
    asyncio.run(app._dispatch_task(task.id))
    asyncio.run(app._dispatch_task(9999))
    assert app.repos.executions.list() == []
    app.db.close()


def test_start_is_idempotent(make_config) -> None:
    config = make_config()
    gateway = FakeGateway()
    app = AgentApp.build(
        config,
        gateway=gateway,
        scheduler=FakeScheduler(),
        llm=FakeLLM(),
        device=FakeDevice(),
    )

    calls = {"boot": 0, "restart": 0}
    original_boot = app.boot.on_start
    original_restart = app.restart_notifier.notify_restart

    async def counting_boot():
        calls["boot"] += 1
        return await original_boot()

    async def counting_restart(*args, **kwargs):
        calls["restart"] += 1
        return await original_restart(*args, **kwargs)

    app.boot.on_start = counting_boot  # type: ignore[method-assign]
    app.restart_notifier.notify_restart = counting_restart  # type: ignore[method-assign]

    async def scenario():
        await app.start()
        await app.start()
        assert gateway.handlers == []

    asyncio.run(scenario())
    assert calls == {"boot": 1, "restart": 1}
    asyncio.run(app.stop())


def test_build_wires_tools_and_services(make_config) -> None:
    config = make_config()
    app = AgentApp.build(
        config, gateway=FakeGateway(), scheduler=FakeScheduler(), llm=FakeLLM()
    )
    names = {tool.name for tool in app.tools.tools()}
    assert {"read_logs", "run_command"} <= names
    assert app.execution is not None
    assert app.supervisor is not None
    app.db.close()


def test_start_rejects_pending_approvals(make_config) -> None:
    app = AgentApp.build(
        make_config(),
        gateway=FakeGateway(),
        scheduler=FakeScheduler(),
        llm=FakeLLM(),
        device=FakeDevice(),
    )
    app.db.migrate()
    approval = app.repos.approvals.create(
        Approval(
            action="delete_file",
            reason="pulizia",
            expires_at="2026-10-25T10:00:00+00:00",
        )
    )

    asyncio.run(app.start())
    try:
        assert app.repos.approvals.get(approval.id).status == "rejected"
    finally:
        asyncio.run(app.stop())


def test_build_exposes_history_query(make_config) -> None:
    app = AgentApp.build(
        make_config(),
        gateway=FakeGateway(),
        scheduler=FakeScheduler(),
        llm=FakeLLM(),
        device=FakeDevice(),
    )
    try:
        assert app.history_query is not None
        assert app.router._history_query is app.history_query
    finally:
        app.db.close()


def test_build_accepts_tz(make_config) -> None:
    from datetime import timezone

    app = AgentApp.build(
        make_config(),
        gateway=FakeGateway(),
        scheduler=FakeScheduler(),
        llm=FakeLLM(),
        device=FakeDevice(),
        tz=timezone.utc,
    )
    try:
        assert app.history_query._tz is timezone.utc
    finally:
        app.db.close()


def test_maintenance_logs_purge_failure(make_config, caplog) -> None:
    import logging

    from agente.errors import StorageError

    app = AgentApp.build(
        make_config(),
        gateway=FakeGateway(),
        scheduler=FakeScheduler(),
        llm=FakeLLM(),
        device=FakeDevice(),
    )
    purged: list[bool] = []

    def broken() -> None:
        raise StorageError("db chiuso")

    app.history.purge_expired = broken  # type: ignore[method-assign]
    app.chat_memory.purge_idle = lambda: purged.append(True)  # type: ignore[method-assign]

    try:
        with caplog.at_level(logging.ERROR, logger="agente.app"):
            app._maintenance()
    finally:
        app.db.close()

    assert purged == [True]
    assert any(record.message == "retention non applicata" for record in caplog.records)


def test_build_exposes_alert_components(make_config) -> None:
    app = AgentApp.build(
        make_config(),
        gateway=FakeGateway(),
        scheduler=FakeScheduler(),
        llm=FakeLLM(),
        device=FakeDevice(),
    )
    try:
        assert app.alerts is not None
        assert app.device_monitor is not None
        assert app.credentials is not None
    finally:
        app.db.close()


def test_start_binds_alert_loop_and_schedules_battery(make_config) -> None:
    config = make_config(battery_check_s=120)
    scheduler = FakeScheduler()
    app = AgentApp.build(
        config,
        gateway=FakeGateway(),
        scheduler=scheduler,
        llm=FakeLLM(),
        device=FakeDevice(),
    )

    asyncio.run(app.start())
    try:
        assert app.alerts._loop is not None
        assert scheduler.battery is not None
        assert scheduler.battery_interval_s == 120
    finally:
        asyncio.run(app.stop())


def test_stop_closes_alert_service(make_config) -> None:
    app = AgentApp.build(
        make_config(),
        gateway=FakeGateway(),
        scheduler=FakeScheduler(),
        llm=FakeLLM(),
        device=FakeDevice(),
    )
    closed: list[bool] = []

    async def close() -> None:
        closed.append(True)

    app.alerts.close = close  # type: ignore[method-assign]

    asyncio.run(app.start())
    asyncio.run(app.stop())

    assert closed == [True]


def test_build_exposes_boot_components(make_config) -> None:
    app = AgentApp.build(
        make_config(),
        gateway=FakeGateway(),
        scheduler=FakeScheduler(),
        llm=FakeLLM(),
        device=FakeDevice(),
    )
    try:
        assert app.boot is not None
        assert app.liveness is not None
        assert app.restart_notifier is not None
    finally:
        app.db.close()


def test_start_schedules_liveness_and_notifies_restart(make_config) -> None:
    config = make_config(liveness_at="07:30")
    gateway = FakeGateway()
    scheduler = FakeScheduler()
    app = AgentApp.build(
        config,
        gateway=gateway,
        scheduler=scheduler,
        llm=FakeLLM(),
        device=FakeDevice(),
    )
    app.db.migrate()
    app.repos.settings.set(
        "last_start_at", "2026-11-02T09:00:00+00:00"
    )

    asyncio.run(app.start())
    try:
        assert scheduler.liveness is not None
        assert scheduler.liveness_at == "07:30"
        assert any("Sono di nuovo attivo" in text for _chat, text in gateway.sent)
    finally:
        asyncio.run(app.stop())


def test_start_uses_boot_recovery(make_config) -> None:
    app = AgentApp.build(
        make_config(),
        gateway=FakeGateway(),
        scheduler=FakeScheduler(),
        llm=FakeLLM(),
        device=FakeDevice(),
    )
    calls: list[str] = []
    original = app.boot.on_start

    async def counting_boot():
        calls.append("boot")
        return await original()

    app.boot.on_start = counting_boot  # type: ignore[method-assign]

    asyncio.run(app.start())
    try:
        assert calls == ["boot"]
    finally:
        asyncio.run(app.stop())


def test_start_stops_when_gateway_fails(make_config, caplog) -> None:
    app = AgentApp.build(
        make_config(),
        gateway=FakeGateway(fail_start=True),
        scheduler=FakeScheduler(),
        llm=FakeLLM(),
        device=FakeDevice(),
    )
    calls: list[str] = []

    async def spy():
        calls.append("boot")

    app.boot.on_start = spy  # type: ignore[method-assign]

    with pytest.raises(OSError):
        asyncio.run(app.start())

    assert calls == []
    assert app.repos.settings.get("last_start_at") is None
    assert any(r.message == "avvio gateway fallito" for r in caplog.records)
    app.db.close()


def test_c07_offline_with_gateway_up_reports_zero(make_config) -> None:
    gateway = FakeGateway()
    app = AgentApp.build(
        make_config(),
        gateway=gateway,
        scheduler=FakeScheduler(),
        llm=FakeLLM(),
        device=FakeDevice(online=False),
    )
    app.db.migrate()
    app.repos.settings.set(
        "last_start_at", "2026-11-02T09:00:00+00:00"
    )

    asyncio.run(app.start())
    try:
        assert any("recuperati 0 compiti" in text for _chat, text in gateway.sent)
    finally:
        asyncio.run(app.stop())
