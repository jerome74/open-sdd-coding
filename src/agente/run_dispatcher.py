"""C-21 Run Dispatcher — lancio manuale di un compito (spec 04).

Regole applicate in codice, mai delegate al LLM: l'admin può lanciare qualsiasi
compito, l'utente autorizzato solo quelli a cui è iscritto (BR-12). Il risultato
va **solo al richiedente** (C-20) e l'esecuzione è registrata da C-09 con
``trigger='manual'`` e ``requested_by`` valorizzato.

Il compito sospeso è eseguibile solo dall'admin (decisione D2 del piano 04): lo
stato `paused` continua a bloccare le occorrenze programmate e non cambia per un
lancio manuale.

I rifiuti precedono l'esecuzione e sono eccezioni tipizzate (``RunRefused``):
l'interfaccia dichiarata ``run(...) -> ExecutionResult`` copre il solo percorso
di successo, C-14 traduce l'eccezione nel messaggio all'utente.
"""

from __future__ import annotations

import logging

from .errors import LockHeldError, RunRefused
from .execution import ExecutionEngine, ExecutionResult
from .role_guard import Role
from .storage.repositories import SubscriptionRepository, Task, UserRepository
from .task_manager import TaskManager

logger = logging.getLogger("agente.run")


class RunDispatcher:
    def __init__(
        self,
        *,
        tasks: TaskManager,
        subscriptions: SubscriptionRepository,
        users: UserRepository,
        execution: ExecutionEngine,
        admin_id: int,
    ) -> None:
        self._tasks = tasks
        self._subscriptions = subscriptions
        self._users = users
        self._execution = execution
        self._admin_id = admin_id

    async def run(
        self, requester_role: Role, requester_id: int, task_name: str
    ) -> ExecutionResult:
        """Esegue il compito richiesto o solleva ``RunRefused``."""
        if requester_role is Role.UNKNOWN:
            raise RunRefused(
                "Utente non autorizzato: il lancio è riservato all'amministratore e "
                "agli utenti autorizzati.",
                reason="forbidden",
            )
        name = (task_name or "").strip()
        if not name:
            raise RunRefused(
                "Indica il compito da lanciare: /run <nome>.", reason="missing_name"
            )
        task = self._tasks.find(name)
        if task is None or task.id is None:
            raise RunRefused(
                self._not_found(name, requester_role, requester_id), reason="not_found"
            )
        self._authorize(task, requester_role, requester_id)
        try:
            result = await self._execution.execute(task, "manual", requester_id)
        except LockHeldError:
            raise RunRefused(
                f"Il compito «{task.name}» è già in esecuzione: lancio rifiutato.",
                reason="busy",
            ) from None
        logger.info(
            "compito lanciato manualmente",
            extra={
                "task_id": task.id,
                "requester_id": requester_id,
                "outcome": result.outcome,
            },
        )
        return result

    # --- autorizzazione ---------------------------------------------------

    def _authorize(self, task: Task, role: Role, requester_id: int) -> None:
        if role is Role.ADMIN:
            # L'admin lancia qualsiasi compito, anche sospeso (D2).
            return
        user = self._users.get(requester_id)
        if user is None or user.state != "accepted":
            raise RunRefused(
                "Utente non autorizzato a lanciare compiti.", reason="forbidden"
            )
        assert task.id is not None
        if task.id not in self._subscriptions.tasks_for_user(requester_id):
            # Il controllo precede quello sullo stato: non si rivela lo stato di
            # un compito a cui il richiedente non è iscritto (BR-12).
            raise RunRefused(
                f"Non sei iscritto al compito «{task.name}»: lancio rifiutato.",
                reason="forbidden",
            )
        if task.state != "active":
            raise RunRefused(
                f"Il compito «{task.name}» è sospeso: "
                "chiedi all'amministratore di riattivarlo.",
                reason="paused",
            )

    def _not_found(self, name: str, role: Role, requester_id: int) -> str:
        message = f"Compito non trovato: «{name}»."
        available = [view.task.name for view in self._tasks.list(role, requester_id)]
        if available:
            message += "\nCompiti disponibili: " + ", ".join(available) + "."
        return message
