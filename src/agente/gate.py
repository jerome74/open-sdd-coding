"""C-27 Action Gate — classificazione e conferma obbligatoria (spec 06).

Il gate è l'unico punto in cui un'azione richiesta dal modello diventa un
effetto sul telefono. Regola invariabile: nessuna azione modificante è eseguita
senza approvazione esplicita dell'amministratore (BR-2, A5); lettura e ricerca
web non richiedono conferma (A4).

Classificazione (D1): whitelist dai metadati di C-08, nessuna euristica.
``requires_approval`` è la fonte di verità; la registrazione impedisce metadati
contraddittori. Uno strumento sconosciuto non viene eseguito e non produce una
richiesta di conferma: non c'è nulla da autorizzare.

L'attesa dell'approvazione non blocca l'event loop. L'handler sincrono gira in
un thread; la rilettura di stato e scadenza avviene invece nell'event loop,
prima dell'offload, perché la connessione SQLite non è condivisibile tra thread.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .approvals import ApprovalManager
from .errors import GateError, SearchError
from .storage.repositories import Approval
from .tools import Tool, ToolRegistry

logger = logging.getLogger("agente.gate")

MAX_OUTPUT_CHARS = 20_000
MAX_DESCRIPTION_CHARS = 300


@dataclass(frozen=True)
class ToolAction:
    """Azione richiesta dal modello, pronta per la classificazione."""

    tool: str
    arguments: dict[str, Any]
    context: Any
    reason: str = ""
    requested_by: int | None = None


@dataclass(frozen=True)
class Gate:
    """Esito della classificazione: ``read_only``, ``modifying`` o ``unknown``."""

    kind: str
    tool: Tool | None = None


class ActionGate:
    def __init__(
        self,
        tools: ToolRegistry,
        approvals: ApprovalManager,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._tools = tools
        self._approvals = approvals
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # --- interfaccia dichiarata ------------------------------------------

    def classify(self, action: ToolAction) -> Gate:
        tool = self._tools.get(action.tool)
        if tool is None:
            return Gate("unknown", None)
        return Gate("read_only" if tool.read_only else "modifying", tool)

    def execute_if_allowed(self, action: ToolAction, approval: Approval | None) -> Any:
        """Esegue l'handler; richiede un'approvazione già validata se modificante."""
        gate = self.classify(action)
        if gate.tool is None or gate.tool.handler is None:
            raise GateError(f"strumento non disponibile: {action.tool}")
        arguments = dict(action.arguments or {})
        if gate.kind == "modifying":
            if (
                approval is None
                or approval.status != "approved"
                or self._is_expired(approval)
            ):
                raise GateError(
                    f"approvazione admin richiesta per: {action.tool}"
                )
            return gate.tool.handler(action.context, arguments, approved=True)
        return gate.tool.handler(action.context, arguments)

    # --- orchestrazione ---------------------------------------------------

    async def run(self, action: ToolAction) -> str:
        gate = self.classify(action)
        logger.info(
            "gate: classificazione",
            extra={"tool": action.tool, "kind": gate.kind},
        )
        if gate.kind == "unknown":
            logger.info("gate: rifiuto", extra={"tool": action.tool, "reason": "unknown"})
            return f"strumento non disponibile: {action.tool}"
        if gate.kind == "read_only":
            return await self._execute(action, None)

        approval = await self._approvals.request(
            action=_describe(action),
            reason=_clip(action.reason),
            requester=action.requested_by,
        )
        if approval.status != "approved" or not self._approvals.is_executable(approval):
            logger.info(
                "gate: rifiuto",
                extra={"tool": action.tool, "reason": approval.status},
            )
            return (
                "azione non eseguita: approvazione dell'amministratore non concessa."
            )
        logger.info("gate: esecuzione approvata", extra={"tool": action.tool})
        return await self._execute(action, approval)

    async def _execute(self, action: ToolAction, approval: Approval | None) -> str:
        try:
            output = await asyncio.to_thread(
                self.execute_if_allowed, action, approval
            )
        except SearchError as exc:
            # V-12: la ricerca non disponibile è un esito, non un guasto del compito.
            logger.warning(
                "gate: ricerca web non disponibile", extra={"error": str(exc)}
            )
            return f"errore dello strumento: {exc}"
        text = output if isinstance(output, str) else str(output)
        if len(text) > MAX_OUTPUT_CHARS:
            logger.info(
                "gate: output troncato",
                extra={"tool": action.tool, "chars": len(text)},
            )
            text = text[:MAX_OUTPUT_CHARS] + "\n[output troncato]"
        return text


    def _is_expired(self, approval: Approval) -> bool:
        moment = _parse(approval.expires_at)
        # Scadenza illeggibile: fail-safe, non eseguire.
        return moment is None or self._clock() >= moment


def _parse(value: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _describe(action: ToolAction) -> str:
    try:
        arguments = json.dumps(action.arguments, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        arguments = str(action.arguments)
    return _clip(f"{action.tool} {arguments}")


def _clip(text: str) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= MAX_DESCRIPTION_CHARS:
        return cleaned
    return cleaned[:MAX_DESCRIPTION_CHARS] + "…"
