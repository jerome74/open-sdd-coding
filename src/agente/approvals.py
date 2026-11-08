"""C-28 Approval Manager — richieste di conferma con timeout (spec 06).

Il manager possiede l'intero ciclo di vita di una richiesta:

1. crea la riga in ``approvals`` (C-02), con scadenza ``limits.approval_timeout_s``
   (BR-3, 15 minuti);
2. registra un waiter e chiede a C-10 di inviare i bottoni all'admin;
3. attende la risoluzione o il timeout;
4. su timeout, cancellazione o errore di invio marca ``rejected``;
5. all'avvio scarta tutte le richieste rimaste ``pending`` (D4).

Solo l'admin può risolvere (A5): la verifica è qui, non solo nel router, così il
gate non dipende dal percorso di ingresso. Una richiesta approvata ma scaduta
non è eseguibile (``is_executable``), e un'approvazione senza waiter viene
rifiutata: nessuna azione sopravvive al processo che l'ha richiesta.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from .errors import StorageError
from .notifications import NotificationService
from .role_guard import Role, RoleGuard
from .storage.repositories import Approval, ApprovalRepository

logger = logging.getLogger("agente.approvals")

DECISIONS = ("approved", "rejected")


@dataclass
class _Waiter:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    created_monotonic: float = 0.0


class ApprovalManager:
    def __init__(
        self,
        approvals: ApprovalRepository,
        notifications: NotificationService,
        roles: RoleGuard,
        *,
        timeout_s: int = 900,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._approvals = approvals
        self._notifications = notifications
        self._roles = roles
        self._timeout_s = timeout_s
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._waiters: dict[int, _Waiter] = {}

    # --- ciclo di vita ----------------------------------------------------

    def recover_pending(self) -> int:
        """Scarta le richieste rimaste aperte da un processo precedente (D4)."""
        count = self._approvals.reject_pending(self._now())
        if count:
            logger.info("approvazioni pendenti scartate all'avvio", extra={"count": count})
        return count

    async def request(
        self,
        *,
        action: str,
        reason: str,
        requester: int | None,
    ) -> Approval:
        """Crea, invia e attende una richiesta; restituisce l'esito risolto."""
        approval = self._notifications.create_approval(
            action=action,
            reason=reason,
            requested_by=requester,
            expires_at=(
                self._clock() + timedelta(seconds=self._timeout_s)
            ).isoformat(timespec="seconds"),
        )
        if approval.id is None:
            raise StorageError("richiesta di approvazione non registrata")
        approval_id = approval.id
        waiter = _Waiter(created_monotonic=time.monotonic())
        self._waiters[approval_id] = waiter
        try:
            try:
                await self._notifications.send_approval(approval)
            except asyncio.CancelledError:
                self._reject(approval_id)
                raise
            except Exception:
                # Nessun bottone utilizzabile: la richiesta non deve restare aperta.
                self._reject(approval_id)
                raise

            remaining = max(
                0.0, (self._expiry(approval) - self._clock()).total_seconds()
            )
            try:
                await asyncio.wait_for(waiter.event.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                self._reject(approval_id)
                logger.info("approvazione scaduta", extra={"approval_id": approval_id})
            except asyncio.CancelledError:
                self._reject(approval_id)
                raise
        finally:
            self._waiters.pop(approval_id, None)

        current = self._approvals.get(approval_id)
        if current is None:
            raise StorageError(f"approvazione scomparsa: {approval_id}")
        return current

    def resolve(self, approval_id: int, decision: str, *, by_user_id: int) -> bool:
        """Risolve una richiesta; solo l'admin, solo se ancora valida."""
        if decision not in DECISIONS:
            raise ValueError(f"esito di approvazione non ammesso: {decision}")
        if self._roles.resolve_role(by_user_id) is not Role.ADMIN:
            logger.warning(
                "approvazione rifiutata: utente non amministratore",
                extra={"approval_id": approval_id, "user_id": by_user_id},
            )
            return False

        approval = self._approvals.get(approval_id)
        if approval is None or approval.status != "pending":
            logger.info(
                "approvazione non risolvibile",
                extra={"approval_id": approval_id, "status": None if approval is None else approval.status},
            )
            return False
        if self._is_expired(approval):
            self._approvals.resolve(approval_id, "rejected", self._now())
            logger.info("approvazione scaduta alla risoluzione", extra={"approval_id": approval_id})
            return False

        waiter = self._waiters.get(approval_id)
        if waiter is None:
            # Nessun processo attende: fail-safe, non autorizzare nulla.
            self._approvals.resolve(approval_id, "rejected", self._now())
            logger.warning(
                "approvazione senza waiter: rifiutata", extra={"approval_id": approval_id}
            )
            return False

        self._approvals.resolve(approval_id, decision, self._now())
        waiter.event.set()
        logger.info(
            "approvazione risolta",
            extra={
                "approval_id": approval_id,
                "decision": decision,
                "by_user_id": by_user_id,
                "duration_ms": round(
                    (time.monotonic() - waiter.created_monotonic) * 1000
                ),
            },
        )
        return True

    def is_executable(self, approval: Approval) -> bool:
        """Rilegge la riga e verifica stato approvato e non scaduto (P-A-07)."""
        if approval.id is None:
            return False
        current = self._approvals.get(approval.id)
        return (
            current is not None
            and current.status == "approved"
            and not self._is_expired(current)
        )

    # --- supporto ---------------------------------------------------------

    def _reject(self, approval_id: int) -> None:
        self._approvals.resolve(approval_id, "rejected", self._now())

    def _now(self) -> str:
        return self._clock().isoformat(timespec="seconds")

    def _expiry(self, approval: Approval) -> datetime:
        moment = _parse(approval.expires_at)
        if moment is None:
            # Scadenza illeggibile: trattata come già scaduta (fail-safe).
            return self._clock() - timedelta(seconds=1)
        return moment

    def _is_expired(self, approval: Approval) -> bool:
        return self._clock() >= self._expiry(approval)


def _parse(value: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)
