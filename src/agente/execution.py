"""C-09 Execution Engine — lock, contesto, LLM, tool, consegna, esito (spec 03).

Flusso 1: il job C-06 arriva qui; l'engine esegue il compito con C-05, esegue
gli strumenti attraverso C-08, consegna il risultato con C-20 e registra
l'esito con C-11. BR-4 (timeout 10 minuti) racchiude ragionamento, tool e
consegna.

Spec 06: tutti gli strumenti sono esposti al modello; l'invocazione passa dal
gate C-27, che classifica read-only/modificante, chiede conferma all'admin e
restituisce un esito di tool. Un'azione rifiutata non interrompe il compito:
il modello prosegue o comunica l'impossibilità (V-08). Anche un errore di
ricerca web è un esito di tool (V-12). Senza gate resta il comportamento
fail-safe di item 03: solo read-only esposti.

Retry BR-8 (spec 03 D5): nessun retry esterno. C-05 ritenta le chiamate LLM e
C-10/C-03 ritentano gli invii Telegram; un fallimento persistente produce esito
``errore`` e avviso all'admin.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .alerts import AlertService
from .delivery import DeliveryService
from .errors import (
    DeliveryError,
    LockHeldError,
    LLMCredentialsError,
    LLMError,
    LogAccessError,
    ToolExecutionError,
)
from .gate import ActionGate, ToolAction
from .history import HistoryService
from .llm import LLMClient, assistant_message
from .notifications import NotificationService
from .storage.repositories import Task
from .task_lock import TaskLock
from .tools import Tool, ToolRegistry

logger = logging.getLogger("agente.execution")

# P-A-08: limiti del loop di tool calling, non dichiarati dalla spec.
MAX_TOOL_ROUNDS = 5
MAX_TOOL_OUTPUT_CHARS = 20_000

_EXECUTION_SYSTEM_PROMPT = (
    "Sei l'agente personale del proprietario. Esegui il compito usando gli "
    "strumenti disponibili quando servono dati reali; non inventare dati. "
    "Rispondi in italiano con il risultato da consegnare, senza preamboli."
)


@dataclass(frozen=True)
class ExecutionResult:
    execution_id: int
    task_id: int
    outcome: str
    started_at: str
    finished_at: str
    summary: str | None
    # P-A-07: testo completo per C-20; `summary` resta troncato per lo storico.
    text: str = ""


class ExecutionEngine:
    def __init__(
        self,
        llm: LLMClient,
        history: HistoryService,
        notifications: NotificationService,
        *,
        timeout_s: float = 600.0,
        clock: Callable[[], datetime] | None = None,
        tools: ToolRegistry | None = None,
        delivery: DeliveryService | None = None,
        lock: TaskLock | None = None,
        gate: ActionGate | None = None,
        alerts: AlertService | None = None,
    ) -> None:
        self._llm = llm
        self._history = history
        self._notifications = notifications
        self._timeout_s = timeout_s
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._tools = tools
        self._delivery = delivery
        self._lock = lock or TaskLock()
        self._gate = gate
        self._alerts = alerts

    def is_running(self, task_id: int) -> bool:
        return self._lock.held(task_id)

    async def execute(
        self,
        task: Task,
        trigger: str,
        requester: int | None = None,
    ) -> ExecutionResult:
        if task.id is None:
            raise ValueError("compito senza id")
        if trigger not in ("scheduled", "manual", "recovery"):
            raise ValueError(f"innesco non ammesso: {trigger}")

        lock = self._lock
        if not lock.acquire(task.id):
            raise LockHeldError(f"esecuzione già in corso per il compito {task.id}")

        try:
            started_mono = time.monotonic()
            started = self._clock().isoformat(timespec="seconds")
            logger.info(
                "esecuzione avviata",
                extra={"task_id": task.id, "trigger": trigger},
            )
            execution = self._history.record(
                task_id=task.id,
                trigger=trigger,
                requested_by=requester,
                started_at=started,
            )
            if execution.id is None:
                raise RuntimeError("esecuzione non registrata")
            # Il risultato manuale va solo al richiedente (spec 04, C-20).
            requested_by = requester if trigger == "manual" else None
            # P-A-05: l'approvazione nasce dal richiedente manuale o dal
            # creatore del compito; i bottoni vanno comunque all'admin.
            approval_requester = (
                requester if trigger == "manual" else task.created_by
            )
            text = ""
            try:
                text = await asyncio.wait_for(
                    self._work(
                        task,
                        requested_by=requested_by,
                        approval_requester=approval_requester,
                    ),
                    timeout=self._timeout_s,
                )
                outcome, summary = "ok", _clip(text)
            except asyncio.TimeoutError:
                outcome, summary = "interrotto", f"timeout dopo {self._timeout_s:.0f}s"
                logger.warning(
                    "esecuzione interrotta", extra={"task_id": task.id, "reason": "timeout"}
                )
                await self._task_alert(
                    "task_timeout",
                    {"task": task.name, "timeout_s": self._timeout_s},
                    f"Compito {task.name}: interrotto per timeout "
                    f"({self._timeout_s:.0f}s)",
                )
            except LLMCredentialsError as exc:
                # C-38 è l'unico produttore dell'avviso di credenziale:
                # C-09 registra l'esito e non invia task_failed/credential.
                outcome, summary = "errore", _clip(f"{type(exc).__name__}: {exc}")
                logger.error(
                    "esecuzione fallita per credenziali",
                    extra={"task_id": task.id, "status": getattr(exc, "status", None)},
                )
            except Exception as exc:  # noqa: BLE001 - l'esito deve essere registrato
                outcome, summary = "errore", _clip(f"{type(exc).__name__}: {exc}")
                logger.error(
                    "esecuzione fallita",
                    extra={"task_id": task.id, "error": type(exc).__name__},
                )
                await self._task_alert(
                    "task_failed",
                    {"task": task.name, "reason": type(exc).__name__},
                    f"Compito {task.name}: esecuzione fallita "
                    f"({type(exc).__name__})",
                )
            finished = self._clock().isoformat(timespec="seconds")
            self._history.finish(execution.id, outcome=outcome, summary=summary)
            logger.info(
                "esecuzione conclusa",
                extra={
                    "task_id": task.id,
                    "outcome": outcome,
                    "duration_s": round(time.monotonic() - started_mono, 3),
                },
            )
            return ExecutionResult(
                execution_id=execution.id,
                task_id=task.id,
                outcome=outcome,
                started_at=started,
                finished_at=finished,
                summary=summary,
                text=text,
            )
        finally:
            # Anche su errore o timeout il compito torna disponibile (AC-03).
            lock.release(task.id)

    # --- lavoro interno ---------------------------------------------------

    async def _work(
        self,
        task: Task,
        *,
        requested_by: int | None = None,
        approval_requester: int | None = None,
    ) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _EXECUTION_SYSTEM_PROMPT},
            {"role": "user", "content": task.instructions},
        ]
        # P-A-20: rifiuti dell'allowlist accumulati per questa esecuzione, non
        # sul motore: due compiti concorrenti non si mescolano.
        refusals: list[str] = []
        schemas = self._tool_schemas()
        for _ in range(MAX_TOOL_ROUNDS):
            response = await asyncio.to_thread(
                self._llm.chat, messages, schemas or None
            )
            if not response.tool_calls:
                text = (response.text or "").strip()
                if not text:
                    raise LLMError("risposta vuota dal modello")
                if refusals:
                    # Nota deterministica: l'admin è informato anche se il
                    # modello non cita i percorsi rifiutati (AC-02).
                    text = f"Log non autorizzati: {', '.join(refusals)}\n{text}"
                await self._deliver(task, text, requested_by=requested_by)
                return text
            messages.append(assistant_message(response))
            for call in response.tool_calls:
                output = await self._invoke_tool(
                    task,
                    call.name,
                    call.arguments,
                    requested_by=approval_requester,
                    refusals=refusals,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id or call.name,
                        "content": output,
                    }
                )
        raise LLMError(f"troppi cicli di tool calling (max {MAX_TOOL_ROUNDS})")

    def _tool_schemas(self) -> list[dict[str, Any]]:
        if self._tools is None:
            return []
        tools = self._tools.tools()
        if self._gate is None:
            # P-A-15: senza gate resta il fail-safe di item 03.
            tools = [tool for tool in tools if tool.read_only]
        return [tool.schema() for tool in tools]

    async def _invoke_tool(
        self,
        task: Task,
        name: str,
        arguments: dict[str, Any],
        *,
        requested_by: int | None = None,
        refusals: list[str] | None = None,
    ) -> str:
        try:
            if self._gate is not None:
                action = ToolAction(
                    tool=name,
                    arguments=dict(arguments or {}),
                    context=task,
                    reason=task.instructions,
                    requested_by=requested_by,
                )
                return await self._gate.run(action)

            tool: Tool | None = (
                self._tools.get(name) if self._tools is not None else None
            )
            if tool is None:
                raise ToolExecutionError(f"strumento sconosciuto: {name}")
            if not tool.read_only:
                raise ToolExecutionError(
                    f"strumento non eseguibile senza approvazione: {name}"
                )
            if tool.handler is None:
                raise ToolExecutionError(f"strumento senza handler: {name}")
            logger.info("tool invocato", extra={"task_id": task.id, "tool": name})
            output = tool.handler(task, dict(arguments or {}))
            text = output if isinstance(output, str) else str(output)
            if len(text) > MAX_TOOL_OUTPUT_CHARS:
                logger.info(
                    "output tool troncato",
                    extra={"task_id": task.id, "tool": name, "chars": len(text)},
                )
                text = text[:MAX_TOOL_OUTPUT_CHARS] + "\n[output troncato]"
            return text
        except LogAccessError as exc:
            # V-04/V-09: percorso non autorizzato = esito di tool, non guasto.
            for path in exc.refused:
                if refusals is not None and path not in refusals:
                    refusals.append(path)
            await self._alert(
                f"Log non autorizzati per il compito {task.name}: "
                f"{', '.join(exc.refused)}"
            )
            return exc.rendered

    async def _deliver(
        self, task: Task, text: str, *, requested_by: int | None = None
    ) -> None:
        if self._delivery is None:
            return
        report = await self._delivery.deliver_text(
            task, text, requested_by=requested_by
        )
        if report.failed:
            recipients = ", ".join(str(user_id) for user_id in report.failed)
            raise DeliveryError(
                f"consegna fallita a: {recipients}", failed=report.failed
            )

    async def _task_alert(
        self, kind: str, detail: dict[str, Any], fallback: str
    ) -> None:
        """Avviso di sistema via C-36, con fallback diretto nei test."""
        if self._alerts is not None:
            await self._alerts.alert(kind, detail)
            return
        await self._alert(fallback)

    async def _alert(self, text: str) -> None:
        """Avviso admin best effort: un invio fallito non cambia l'esito."""
        try:
            await self._notifications.alert_admin(text)
        except Exception:  # noqa: BLE001 - l'esito è già determinato
            logger.exception("avviso admin non inviato")



def _clip(text: str, limit: int = 500) -> str:
    return text if len(text) <= limit else text[:limit]
