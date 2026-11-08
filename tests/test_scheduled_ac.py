"""AC-01…AC-03 di spec 03, end-to-end sull'applicazione con dipendenze finte."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path

from agente.app import AgentApp
from agente.llm import LLMResponse
from agente.schedule_interpreter import Schedule
from agente.storage.repositories import User
from agente.task_manager import TaskDraft
from conftest import ADMIN_ID, USER_ID

LOCAL = datetime.now().astimezone().tzinfo
NOW = datetime(2026, 10, 24, 9, 30, tzinfo=LOCAL)
MORNING = datetime(2026, 10, 24, 8, 0, tzinfo=LOCAL)
UPCOMING = datetime(2026, 10, 25, 8, 0, tzinfo=LOCAL)


class AppGateway:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.deleted: list[tuple[int, int]] = []
        self.started = False
        self.stopped = False
        self._next_id = 0

    def set_inbound_handler(self, handler) -> None:
        self.inbound = handler

    def add_handler(self, handler, group: int = 0) -> None:
        return None

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send(self, chat_id, text, keyboard=None) -> int:
        self._next_id += 1
        self.sent.append((chat_id, text))
        return self._next_id

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))


class AppScheduler:
    def __init__(self) -> None:
        self.jobs: dict[int, object] = {}
        self.next_runs: dict[int, datetime] = {}
        self.upcoming = UPCOMING
        self.paused = False
        self.resumed = False
        self.maintenance = None
        self.connectivity = None
        self.battery = None
        self.liveness = None

    def set_dispatcher(self, dispatcher) -> None:
        self.dispatcher = dispatcher

    def schedule_task(self, task, trigger) -> str:
        self.jobs[task.id] = trigger
        self.next_runs[task.id] = self.upcoming
        return f"task:{task.id}"

    def unschedule_task(self, task_id: int) -> None:
        self.jobs.pop(task_id, None)
        self.next_runs.pop(task_id, None)

    def next_run(self, task_id: int):
        return self.next_runs.get(task_id)

    def start(self, *, paused: bool = False) -> None:
        self.paused = paused

    def resume(self) -> None:
        self.resumed = True

    def shutdown(self, wait: bool = False) -> None:
        return None

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


class AppDevice:
    def __init__(self, online: bool = True) -> None:
        self.online = online

    def is_online(self) -> bool:
        return self.online

    def record_last_contact(self, settings, when=None) -> str:
        moment = (when or NOW).isoformat(timespec="seconds")
        settings.set("last_contact_at", moment)
        return moment


class AppLLM:
    def __init__(self, text: str = "risultato settimanale", *, delay: float = 0.0) -> None:
        self.text = text
        self.delay = delay
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return LLMResponse(text=self.text)

    def summarize(self, text: str) -> str:
        return self.text


def build_app(make_config, *, online: bool = True, llm: AppLLM | None = None, **limits):
    config = make_config(admin_id=ADMIN_ID, **limits)
    gateway = AppGateway()
    app = AgentApp.build(
        config,
        gateway=gateway,
        scheduler=AppScheduler(),
        llm=llm or AppLLM(),
        device=AppDevice(online),
        clock=lambda: NOW,
    )
    app.db.migrate()
    app.repos.users.upsert(User(telegram_id=USER_ID, username="utente", state="accepted"))
    return app


def _task(app) -> object:
    return app.tasks.create(
        TaskDraft(
            name="rassegna",
            instructions="riassumi i titoli",
            schedule=Schedule("orario", "08:00"),
            recipients=(USER_ID,),
        )
    )


def test_ac01_scheduled_task_delivers_to_all_recipients(make_config) -> None:
    app = build_app(make_config)
    task = _task(app)
    app.gateway.sent.clear()

    asyncio.run(app._dispatch_task(task.id))

    assert [chat_id for chat_id, _ in app.gateway.sent] == [ADMIN_ID, USER_ID]
    assert all(text == "risultato settimanale" for _, text in app.gateway.sent)
    stored = app.repos.executions.list(task_id=task.id)
    assert len(stored) == 1
    assert (stored[0].trigger, stored[0].outcome) == ("scheduled", "ok")
    app.db.close()


def test_ac02_offline_missed_occurrence_recovered_once(make_config) -> None:
    app = build_app(make_config)
    task = _task(app)
    app.repos.settings.set(
        app.registrar.setting_key(task.id), MORNING.isoformat(timespec="seconds")
    )
    app.gateway.sent.clear()

    results = asyncio.run(app.recovery.recover_missed())

    assert len(results) == 1
    stored = app.repos.executions.list(task_id=task.id)
    assert [execution.trigger for execution in stored] == ["recovery"]
    assert stored[0].outcome == "ok"
    assert [chat_id for chat_id, _ in app.gateway.sent] == [ADMIN_ID, USER_ID]
    assert asyncio.run(app.recovery.recover_missed()) == []
    assert len(app.repos.executions.list(task_id=task.id)) == 1
    app.db.close()


def test_ac02_start_recovers_before_resuming_jobs(make_config) -> None:
    app = build_app(make_config)
    task = _task(app)
    app.scheduler.next_runs[task.id] = MORNING

    asyncio.run(app.start())
    try:
        stored = app.repos.executions.list(task_id=task.id)
        assert [execution.trigger for execution in stored] == ["recovery"]
        assert app.scheduler.paused is True
        assert app.scheduler.resumed is True
        assert app.scheduler.connectivity is not None
    finally:
        asyncio.run(app.stop())


def test_ac03_timeout_marks_interrupted_and_alerts_admin(make_config) -> None:
    app = build_app(make_config, llm=AppLLM(delay=1.5), execution_timeout_s=1)
    task = _task(app)
    app.gateway.sent.clear()

    asyncio.run(app._dispatch_task(task.id))

    stored = app.repos.executions.list(task_id=task.id)
    assert [execution.outcome for execution in stored] == ["interrotto"]
    alerts = [text for chat_id, text in app.gateway.sent if chat_id == ADMIN_ID]
    assert any("timeout" in text for text in alerts)
    app.db.close()


def test_offline_job_leaves_the_marker_for_recovery(make_config) -> None:
    app = build_app(make_config, online=False)
    task = _task(app)
    app.repos.settings.set(
        app.registrar.setting_key(task.id), MORNING.isoformat(timespec="seconds")
    )

    asyncio.run(app._dispatch_task(task.id))

    assert app.repos.executions.list(task_id=task.id) == []
    assert app.registrar.next_run(task.id) == MORNING
    app.db.close()


def test_connectivity_job_recovers_after_network_returns(make_config) -> None:
    app = build_app(make_config, online=False)
    task = _task(app)
    app.repos.settings.set(
        app.registrar.setting_key(task.id), MORNING.isoformat(timespec="seconds")
    )

    asyncio.run(app.recovery.check_connectivity())
    app.device.online = True
    results = asyncio.run(app.recovery.check_connectivity())

    assert len(results) == 1
    assert len(app.repos.executions.list(task_id=task.id)) == 1
    app.db.close()
