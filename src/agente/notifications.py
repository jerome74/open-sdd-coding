"""C-10 Notification Service — risultati, avvisi, richieste di conferma."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

from .config import Config
from .storage.repositories import Approval, ApprovalRepository

logger = logging.getLogger("agente.notifications")

# Limite della Bot API di Telegram per un singolo messaggio.
MAX_MESSAGE_LENGTH = 4096

Keyboard = Sequence[Sequence[tuple[str, str]]]


class NotificationService:
    def __init__(
        self,
        gateway: Any,
        config: Config,
        approvals: ApprovalRepository,
        *,
        clock: Any = None,
    ) -> None:
        self._gateway = gateway
        self._admin_id = config.admin_telegram_id
        self._approvals = approvals
        self._approval_timeout_s = config.limits.approval_timeout_s
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def notify(
        self,
        recipients: Iterable[int],
        text: str,
        keyboard: Keyboard | None = None,
    ) -> None:
        """Invia il testo ai destinatari; la tastiera va sull'ultimo pezzo.

        Spec 08 (V-09): C-33 ha bisogno di inviare all'admin il pulsante
        «Autorizza» senza parlare direttamente con C-03.
        """
        for recipient in recipients:
            chunks = split_message(text)
            for index, chunk in enumerate(chunks):
                await self._gateway.send(
                    recipient,
                    chunk,
                    keyboard=keyboard if index == len(chunks) - 1 else None,
                )

    async def alert_admin(self, text: str, keyboard: Keyboard | None = None) -> None:
        await self.notify([self._admin_id], text, keyboard=keyboard)

    async def request_approval(
        self,
        *,
        action: str,
        reason: str,
        requested_by: int | None,
    ) -> Approval:
        """Crea la richiesta e la invia (wrapper di compatibilità di spec 01).

        Da spec 06 il ciclo di vita è di C-28: la produzione usa
        ``create_approval`` + ``send_approval``; questo metodo resta per i
        chiamanti esistenti e per i test della fondazione.
        """
        approval = self.create_approval(
            action=action, reason=reason, requested_by=requested_by
        )
        await self.send_approval(approval)
        return approval

    def create_approval(
        self,
        *,
        action: str,
        reason: str,
        requested_by: int | None,
        expires_at: str | None = None,
    ) -> Approval:
        if expires_at is None:
            expires_at = (
                self._clock() + timedelta(seconds=self._approval_timeout_s)
            ).isoformat(timespec="seconds")
        return self._approvals.create(
            Approval(
                action=action,
                reason=reason,
                expires_at=expires_at,
                requested_by=requested_by,
            )
        )

    async def send_approval(self, approval: Approval) -> None:
        """Invia all'admin i bottoni Approva/Rifiuta per una richiesta già creata."""
        keyboard: Keyboard = (
            (
                ("Approva", f"approval:{approval.id}:approve"),
                ("Rifiuta", f"approval:{approval.id}:reject"),
            ),
        )
        await self._gateway.send(
            self._admin_id,
            f"Richiesta di conferma\nAzione: {approval.action}\n"
            f"Motivo: {approval.reason}\nScade: {approval.expires_at}",
            keyboard=keyboard,
        )
        logger.info("richiesta di conferma inviata", extra={"approval_id": approval.id})


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Divide senza perdere caratteri; preferisce i confini di riga."""
    if limit <= 0:
        raise ValueError("limit deve essere positivo")
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks
