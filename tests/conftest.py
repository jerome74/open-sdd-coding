"""Fixture condivise: configurazione tipizzata e app fittizie."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from agente.approvals import ApprovalManager
from agente.authorization_notifier import AuthorizationNotifier
from agente.chat import ChatHandler
from agente.chat_memory import ConversationMemory
from agente.command_router import CommandRouter
from agente.confirmation import ConfirmationFlow
from agente.consent import ConsentFlow
from agente.config import (
    Config,
    DeepSeekConfig,
    LimitsConfig,
    PathsConfig,
    SearchConfig,
    TelegramConfig,
)
from agente.delivery import DeliveryService
from agente.execution import ExecutionEngine
from agente.gate import ActionGate
from agente.history import HistoryService
from agente.history_query import HistoryQuery
from agente.llm import LLMResponse
from agente.notifications import NotificationService
from agente.progress import ProgressIndicator
from agente.role_guard import RoleGuard
from agente.run_dispatcher import RunDispatcher
from agente.schedule_interpreter import ScheduleInterpreter
from agente.storage.db import Database
from agente.storage.repositories import User, repositories
from agente.task_lock import TaskLock
from agente.task_manager import TaskManager
from agente.tools import ToolRegistry
from agente.user_manager import UserManager

ADMIN_ID = 1
USER_ID = 2


@pytest.fixture
def make_config(tmp_path: Path):
    def factory(admin_id: int = 1, search=None, **limits) -> Config:
        return Config(
            admin_telegram_id=admin_id,
            telegram=TelegramConfig(token="test-token"),
            deepseek=DeepSeekConfig(
                model="deepseek-flash",
                api_base="https://api.deepseek.test/v1",
                api_key="test-key",
                max_context_tokens=1000,
            ),
            search=search or SearchConfig(),
            paths=PathsConfig(db=tmp_path / "agente.db", logs=tmp_path / "logs"),
            limits=LimitsConfig(**limits),
        )

    return factory


class FakeGateway:
    """C-03 finto: registra invii, id dei messaggi e cancellazioni."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []
        self.deleted: list[tuple[int, int]] = []
        self._next_id = 100

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


class FakeRegistrar:
    """C-18 finto: registra job creati, aggiornati e rimossi."""

    def __init__(self) -> None:
        self.registered: list[int] = []
        self.updated: list[int] = []
        self.scheduled: list[int] = []
        self.unscheduled: list[int] = []
        self.next_runs: dict[int, object] = {}

    def register(self, task):
        self.registered.append(task.id)
        self.scheduled.append(task.id)
        return f"task:{task.id}"

    def update(self, task):
        self.updated.append(task.id)
        self.scheduled.append(task.id)
        return f"task:{task.id}"

    def unregister(self, task_id: int) -> None:
        self.unscheduled.append(task_id)

    def refresh(self, task_id: int):
        return self.next_runs.get(task_id)

    def next_run(self, task_id: int):
        return self.next_runs.get(task_id)


class FakeLLM:
    """C-05 finto: risponde alla bozza (C-14) e al normalizzatore (C-16)."""

    def __init__(
        self,
        *,
        draft: dict | None = None,
        schedule: dict | None = None,
        error: bool = False,
    ) -> None:
        self.draft = draft if draft is not None else {}
        self.schedule = schedule if schedule is not None else {"type": "ambiguo", "domanda": "?"}
        self.error = error
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.error:
            from agente.errors import LLMError

            raise LLMError("modello non disponibile")
        system = str(messages[0].get("content", ""))
        if "normalizzatore" in system:
            return LLMResponse(text=json.dumps(self.schedule))
        return LLMResponse(text=json.dumps(self.draft))


@dataclass
class TaskHarness:
    config: Config
    db: Database
    repos: object
    gateway: FakeGateway
    registrar: FakeRegistrar
    llm: FakeLLM
    history: HistoryService
    notifications: NotificationService
    approvals: ApprovalManager
    gate: ActionGate
    tools: ToolRegistry
    execution: ExecutionEngine
    delivery: DeliveryService
    lock: TaskLock
    run: RunDispatcher
    manager: TaskManager
    interpreter: ScheduleInterpreter
    confirmations: ConfirmationFlow
    chat: ChatHandler
    user_manager: UserManager
    consent: ConsentFlow
    notifier: AuthorizationNotifier
    history_query: HistoryQuery
    router: CommandRouter


@pytest.fixture
def harness_factory(tmp_path: Path, make_config):
    """App della feature 02 con dipendenze esterne finte (C-03, C-05, C-06)."""

    def factory(*, llm: object | None = None, clock=None, tools=None, search=None, **limits) -> TaskHarness:
        config = make_config(admin_id=ADMIN_ID, search=search, **limits)
        db = Database(tmp_path / "agente.db")
        db.migrate()
        repos = repositories(db.connection)
        repos.users.upsert(User(telegram_id=USER_ID, username="utente", state="accepted"))
        gateway = FakeGateway()
        registrar = FakeRegistrar()
        model = llm or FakeLLM()
        roles = RoleGuard(config, repos.users)
        manager = TaskManager(
            repos.tasks,
            repos.subscriptions,
            repos.users,
            registrar,
            admin_id=ADMIN_ID,
            min_interval_minutes=1,
        )
        interpreter = ScheduleInterpreter(model)
        confirmations = ConfirmationFlow(gateway, timeout_s=5)
        notifications = NotificationService(gateway, config, repos.approvals)
        consent = ConsentFlow(repos.users, notifications, clock=clock)
        notifier = AuthorizationNotifier(notifications, clock=clock)
        approvals = ApprovalManager(
            repos.approvals,
            notifications,
            roles,
            timeout_s=config.limits.approval_timeout_s,
            clock=clock,
        )
        registry = tools or ToolRegistry()
        gate = ActionGate(registry, approvals)
        history = HistoryService(
            repos.executions,
            repos.conversations,
            retention_days=config.limits.history_retention_days,
            chat_memory_hours=config.limits.chat_memory_hours,
            clock=clock,
        )
        delivery = DeliveryService(
            repos.subscriptions, repos.users, notifications, admin_id=ADMIN_ID
        )
        memory = ConversationMemory(
            repos.conversations,
            memory_hours=config.limits.chat_memory_hours,
            context_tokens=config.deepseek.max_context_tokens,
            clock=clock,
        )
        progress = ProgressIndicator(
            gateway, threshold_s=config.limits.chat_progress_s
        )
        lock = TaskLock()
        execution = ExecutionEngine(
            model,
            history,
            notifications,
            timeout_s=config.limits.execution_timeout_s,
            delivery=delivery,
            lock=lock,
            tools=registry,
            gate=gate,
        )
        chat = ChatHandler(
            roles=roles,
            memory=memory,
            llm=model,
            progress=progress,
            gateway=gateway,
            users=repos.users,
            tools=registry,
            admin_id=ADMIN_ID,
            gate=gate,
        )
        user_manager = UserManager(
            repos.users,
            repos.subscriptions,
            repos.tasks,
            consent,
            roles,
        )
        history_query = HistoryQuery(
            history,
            manager,
            retention_days=config.limits.history_retention_days,
            llm=model,
            clock=clock,
            tz=ZoneInfo("Europe/Rome"),
        )
        run = RunDispatcher(
            tasks=manager,
            subscriptions=repos.subscriptions,
            users=repos.users,
            execution=execution,
            admin_id=ADMIN_ID,
        )
        router = CommandRouter(
            roles=roles,
            tasks=manager,
            interpreter=interpreter,
            confirmations=confirmations,
            gateway=gateway,
            llm=model,
            run_dispatcher=run,
            chat=chat,
            approvals=approvals,
            users=user_manager,
            consent=consent,
            notifier=notifier,
            history_query=history_query,
            admin_id=ADMIN_ID,
        )
        return TaskHarness(
            config=config,
            db=db,
            repos=repos,
            gateway=gateway,
            registrar=registrar,
            llm=model,
            history=history,
            notifications=notifications,
            approvals=approvals,
            gate=gate,
            tools=registry,
            execution=execution,
            delivery=delivery,
            lock=lock,
            run=run,
            manager=manager,
            interpreter=interpreter,
            confirmations=confirmations,
            chat=chat,
            user_manager=user_manager,
            consent=consent,
            notifier=notifier,
            history_query=history_query,
            router=router,
        )

    yield factory
