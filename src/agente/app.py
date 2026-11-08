"""Wiring applicativo: config → migrazione → polling → scheduler (spec 01)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Any, Callable, Sequence

from .alerts import AlertService
from .approvals import ApprovalManager
from .authorization_notifier import AuthorizationNotifier
from .boot import BootRecovery
from .chat import ChatHandler
from .chat_memory import ConversationMemory
from .command_router import CommandRouter
from .confirmation import ConfirmationFlow
from .config import Config
from .consent import ConsentFlow
from .credential_monitor import CredentialMonitor
from .delivery import DeliveryService
from .device import DeviceAdapter
from .device_monitor import DeviceMonitor
from .errors import DeviceError, LockHeldError, StorageError
from .execution import ExecutionEngine
from .gate import ActionGate
from .history import HistoryService
from .history_query import HistoryQuery
from .liveness import LivenessScheduler
from .llm import LLMClient
from .notifications import NotificationService
from .progress import ProgressIndicator
from .recovery import RecoveryHandler
from .restart import RestartNotifier
from .role_guard import RoleGuard
from .run_dispatcher import RunDispatcher
from .schedule_interpreter import ScheduleInterpreter
from .schedule_registrar import ScheduleRegistrar
from .scheduler import TaskScheduler
from .storage.db import Database
from .storage.repositories import Repositories, repositories
from .supervisor import Supervisor
from .task_lock import TaskLock
from .task_manager import TaskManager
from .telegram_gateway import TelegramGateway
from .tools import ToolRegistry, default_registry
from .user_manager import UserManager
from .web_search import WebSearchAdapter

logger = logging.getLogger("agente.app")

# Assunzione (piano 01): la spec non dichiara la soglia di stallo del watchdog.
# 5 minuti senza heartbeat = processo in stallo; da validare sul dispositivo.
SUPERVISOR_TIMEOUT_S = 300
HEARTBEAT_INTERVAL_S = 30


@dataclass
class AgentApp:
    config: Config
    db: Database
    repos: Repositories
    gateway: TelegramGateway
    scheduler: TaskScheduler
    llm: LLMClient
    device: DeviceAdapter
    tools: ToolRegistry
    notifications: NotificationService
    alerts: AlertService
    device_monitor: DeviceMonitor
    credentials: CredentialMonitor
    boot: BootRecovery
    liveness: LivenessScheduler
    restart_notifier: RestartNotifier
    search: WebSearchAdapter
    approvals: ApprovalManager
    gate: ActionGate
    history: HistoryService
    chat_memory: ConversationMemory
    progress: ProgressIndicator
    execution: ExecutionEngine
    delivery: DeliveryService
    registrar: ScheduleRegistrar
    recovery: RecoveryHandler
    lock: TaskLock
    run_dispatcher: RunDispatcher
    supervisor: Supervisor
    roles: RoleGuard
    interpreter: ScheduleInterpreter
    tasks: TaskManager
    confirmations: ConfirmationFlow
    chat: ChatHandler
    user_manager: UserManager
    consent: ConsentFlow
    notifier: AuthorizationNotifier
    history_query: HistoryQuery
    router: CommandRouter
    _started: bool = False

    @classmethod
    def build(
        cls,
        config: Config,
        *,
        gateway: TelegramGateway | None = None,
        scheduler: TaskScheduler | None = None,
        llm: LLMClient | None = None,
        device: DeviceAdapter | None = None,
        search: WebSearchAdapter | None = None,
        clock: Callable[[], datetime] | None = None,
        tz: tzinfo | None = None,
    ) -> "AgentApp":
        db = Database(config.paths.db)
        repos = repositories(db.connection)
        roles = RoleGuard(config, repos.users)
        device = device or DeviceAdapter()
        gateway = gateway or TelegramGateway(
            config.telegram.token,
            retry_attempts=config.limits.retry_attempts,
            retry_delay_s=config.limits.retry_delay_s,
        )
        scheduler = scheduler or TaskScheduler(config.paths.db)
        notifications = NotificationService(gateway, config, repos.approvals)
        alerts = AlertService(notifications, repos.settings, clock=clock)
        credentials = CredentialMonitor(alerts)
        liveness = LivenessScheduler(
            notifications,
            repos.settings,
            at=config.limits.liveness_at,
            clock=clock,
        )
        restart_notifier = RestartNotifier(
            notifications, at=config.limits.liveness_at, clock=clock
        )
        device_monitor = DeviceMonitor(
            device,
            repos.settings,
            alerts,
            battery_threshold_pct=config.limits.battery_threshold_pct,
            offline_threshold_s=config.limits.offline_threshold_s,
            clock=clock,
        )
        llm = llm or LLMClient(
            config.deepseek,
            retry_attempts=config.limits.retry_attempts,
            retry_delay_s=config.limits.retry_delay_s,
            on_credentials_error=credentials.on_llm_error,
        )
        consent = ConsentFlow(repos.users, notifications, clock=clock)
        notifier = AuthorizationNotifier(notifications, clock=clock)
        search = search or WebSearchAdapter(
            config.search,
            retry_attempts=config.limits.retry_attempts,
            retry_delay_s=config.limits.retry_delay_s,
        )
        approvals = ApprovalManager(
            repos.approvals,
            notifications,
            roles,
            timeout_s=config.limits.approval_timeout_s,
            clock=clock,
        )
        history = HistoryService(
            repos.executions,
            repos.conversations,
            retention_days=config.limits.history_retention_days,
            chat_memory_hours=config.limits.chat_memory_hours,
            clock=clock,
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
        delivery = DeliveryService(
            repos.subscriptions,
            repos.users,
            notifications,
            admin_id=config.admin_telegram_id,
        )
        tools = default_registry(device, search=search)
        gate = ActionGate(tools, approvals, clock=clock)
        lock = TaskLock()
        execution = ExecutionEngine(
            llm,
            history,
            notifications,
            timeout_s=config.limits.execution_timeout_s,
            tools=tools,
            delivery=delivery,
            lock=lock,
            gate=gate,
            clock=clock,
            alerts=alerts,
        )
        registrar = ScheduleRegistrar(repos.settings, scheduler, clock=clock)
        recovery = RecoveryHandler(
            tasks=repos.tasks,
            registrar=registrar,
            engine=execution,
            history=history,
            monitor=device_monitor,
            clock=clock,
        )
        boot = BootRecovery(
            scheduler=scheduler,
            registrar=registrar,
            tasks=repos.tasks,
            recovery=recovery,
            settings=repos.settings,
            liveness_at=config.limits.liveness_at,
            clock=clock,
        )
        interpreter = ScheduleInterpreter(llm)
        confirmations = ConfirmationFlow(
            gateway, timeout_s=config.limits.approval_timeout_s
        )
        tasks = TaskManager(
            repos.tasks,
            repos.subscriptions,
            repos.users,
            registrar,
            admin_id=config.admin_telegram_id,
            min_interval_minutes=config.limits.min_interval_minutes,
        )
        chat = ChatHandler(
            roles=roles,
            memory=memory,
            llm=llm,
            progress=progress,
            gateway=gateway,
            users=repos.users,
            tools=tools,
            admin_id=config.admin_telegram_id,
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
            tasks,
            retention_days=config.limits.history_retention_days,
            llm=llm,
            clock=clock,
            tz=tz,
        )
        run_dispatcher = RunDispatcher(
            tasks=tasks,
            subscriptions=repos.subscriptions,
            users=repos.users,
            execution=execution,
            admin_id=config.admin_telegram_id,
        )
        router = CommandRouter(
            roles=roles,
            tasks=tasks,
            interpreter=interpreter,
            confirmations=confirmations,
            gateway=gateway,
            llm=llm,
            run_dispatcher=run_dispatcher,
            chat=chat,
            approvals=approvals,
            users=user_manager,
            consent=consent,
            notifier=notifier,
            history_query=history_query,
            admin_id=config.admin_telegram_id,
        )
        return cls(
            config=config,
            db=db,
            repos=repos,
            gateway=gateway,
            scheduler=scheduler,
            llm=llm,
            device=device,
            tools=tools,
            notifications=notifications,
            alerts=alerts,
            device_monitor=device_monitor,
            credentials=credentials,
            boot=boot,
            liveness=liveness,
            restart_notifier=restart_notifier,
            search=search,
            approvals=approvals,
            gate=gate,
            history=history,
            chat_memory=memory,
            progress=progress,
            execution=execution,
            delivery=delivery,
            registrar=registrar,
            recovery=recovery,
            lock=lock,
            run_dispatcher=run_dispatcher,
            supervisor=Supervisor(timeout_s=SUPERVISOR_TIMEOUT_S),
            roles=roles,
            interpreter=interpreter,
            tasks=tasks,
            confirmations=confirmations,
            chat=chat,
            user_manager=user_manager,
            consent=consent,
            notifier=notifier,
            history_query=history_query,
            router=router,
        )

    async def start(self, handlers: Sequence[Any] | None = None) -> None:
        if self._started:
            return
        applied = self.db.migrate()
        logger.info("config caricata", extra={"schema_applied": applied})
        # Spec 10: gli avvisi di credenziale nascono da un worker di C-05.
        self.alerts.bind_loop(asyncio.get_running_loop())
        # Spec 06 D4: nessuna approvazione sopravvive al processo che l'ha creata.
        self.approvals.recover_pending()
        for handler in handlers or ():
            self.gateway.add_handler(handler)
        self.gateway.set_inbound_handler(self.router.route)
        self.scheduler.set_dispatcher(self._dispatch_task)
        # I callback dei job periodici esistono già prima dell'avvio: un job
        # persistito che scatta al boot non trova un global vuoto.
        self.scheduler.schedule_maintenance(self._maintenance)
        self.scheduler.schedule_connectivity(
            self.recovery.check_connectivity,
            interval_s=self.config.limits.connectivity_check_s,
        )
        self.scheduler.schedule_battery(
            self.device_monitor.check_battery,
            interval_s=self.config.limits.battery_check_s,
        )
        self.scheduler.schedule_liveness(
            self.liveness.send_liveness,
            at=self.config.limits.liveness_at,
        )
        try:
            await self.gateway.start()
        except Exception:
            # V-13: il gateway non solleva AgenteError; il loop esterno riavvia.
            logger.error("avvio gateway fallito", exc_info=True)
            raise
        # Spec 11: C-39 carica i job in pausa, recupera e poi riattiva.
        summary = await self.boot.on_start()
        await self.restart_notifier.notify_restart(
            summary, summary.offline_period, summary.liveness_missed
        )
        self.supervisor.heartbeat()
        self._started = True
        logger.info("agente avviato")

    def _maintenance(self) -> None:
        """Job giornaliero: retention esecuzioni/messaggi e conversazioni inattive.

        Spec 09 (C-35): un errore di retention viene loggato e non impedisce la
        pulizia della chat; il job del giorno successivo ritenta.
        """
        try:
            stats = self.history.purge_expired()
        except StorageError as exc:
            logger.error("retention non applicata", extra={"error": str(exc)})
        else:
            logger.info(
                "retention applicata",
                extra={
                    "executions_deleted": stats.executions_deleted,
                    "messages_deleted": stats.messages_deleted,
                },
            )
        try:
            self.chat_memory.purge_idle()
        except StorageError as exc:
            logger.error("pulizia chat non applicata", extra={"error": str(exc)})

    async def _dispatch_task(self, task_id: int) -> None:
        """Job C-06 → C-09: esegue solo compiti attivi, con rete disponibile.

        Se la rete manca l'occorrenza non viene eseguita e il marcatore
        ``next_run`` resta fermo: C-19 la recupera al rientro online (BR-5).
        """
        task = self.repos.tasks.get(task_id)
        if task is None or task.state != "active":
            logger.info("job ignorato", extra={"task_id": task_id})
            return
        try:
            online = await asyncio.to_thread(self.device.is_online)
        except DeviceError as exc:
            logger.warning(
                "stato di rete non leggibile: job non eseguito",
                extra={"task_id": task_id, "error": str(exc)},
            )
            return
        if not online:
            logger.info("occorrenza saltata: rete assente", extra={"task_id": task_id})
            return
        try:
            await self.execution.execute(task, "scheduled")
        except LockHeldError:
            logger.info("esecuzione già in corso", extra={"task_id": task_id})
        finally:
            self.registrar.refresh(task_id)

    async def stop(self) -> None:
        if not self._started:
            return
        self.scheduler.shutdown(wait=False)
        await self.alerts.close()
        await self.gateway.stop()
        self.db.close()
        self._started = False
        logger.info("agente fermato")


async def run(config: Config) -> None:
    """Avvia l'agente fino a cancellazione (usato da ``python -m agente``)."""
    app = AgentApp.build(config)
    await app.start()
    app.supervisor.start_thread()
    heartbeat = asyncio.create_task(_heartbeat_loop(app.supervisor))
    try:
        await asyncio.Event().wait()
    finally:
        heartbeat.cancel()
        app.supervisor.stop_thread()
        await app.stop()


async def _heartbeat_loop(supervisor: Supervisor, interval_s: float = HEARTBEAT_INTERVAL_S) -> None:
    while True:
        await asyncio.sleep(interval_s)
        supervisor.heartbeat()
