"""C-20 Delivery Service — destinatari e invio del risultato (spec 03/04).

Calcola i destinatari del compito — admin implicito (decisione #7) più utenti
iscritti ancora ``accepted`` — e delega l'invio a C-10, che applica split dei
messaggi e retry BR-8. L'admin non è un record in ``users``: è sempre incluso e
non viene iscritto (spec 01, decisione #7).

Per il lancio manuale (spec 04) il risultato va **solo al richiedente**: con
``requested_by`` valorizzato gli iscritti al compito non ricevono nulla.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from .errors import DeliveryError, TelegramError
from .notifications import NotificationService
from .storage.repositories import SubscriptionRepository, Task, UserRepository

logger = logging.getLogger("agente.delivery")


class ResultLike(Protocol):
    """Forma minima del risultato di C-09 accettata da C-20."""

    text: str
    summary: str | None


@dataclass(frozen=True)
class DeliveryReport:
    sent: tuple[int, ...] = ()
    failed: tuple[int, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.failed


class DeliveryService:
    def __init__(
        self,
        subscriptions: SubscriptionRepository,
        users: UserRepository,
        notifications: NotificationService,
        *,
        admin_id: int,
    ) -> None:
        self._subscriptions = subscriptions
        self._users = users
        self._notifications = notifications
        self._admin_id = admin_id

    def recipients(
        self, task: Task, *, requested_by: int | None = None
    ) -> tuple[int, ...]:
        """Admin sempre incluso, poi iscritti ancora autorizzati (BR-12).

        Con ``requested_by`` (lancio manuale, spec 04) il risultato va **solo al
        richiedente**: il compito non è un'esecuzione programmata e gli iscritti
        non hanno chiesto nulla.
        """
        if requested_by is not None:
            return self._manual_recipient(requested_by)
        recipients = [self._admin_id]
        for user_id in self._subscriptions.users_for_task(task.id):
            if user_id == self._admin_id or user_id in recipients:
                continue
            user = self._users.get(user_id)
            if user is None or user.state != "accepted":
                logger.info(
                    "destinatario escluso: non autorizzato",
                    extra={"task_id": task.id, "user_id": user_id},
                )
                continue
            recipients.append(user_id)
        return tuple(recipients)

    def _manual_recipient(self, requester_id: int) -> tuple[int, ...]:
        """Richiedente del lancio manuale: admin o utente ancora `accepted`."""
        if requester_id == self._admin_id:
            return (requester_id,)
        user = self._users.get(requester_id)
        if user is None or user.state != "accepted":
            logger.warning(
                "richiedente non autorizzato a ricevere il risultato",
                extra={"user_id": requester_id},
            )
            raise DeliveryError("richiedente non autorizzato a ricevere il risultato")
        return (requester_id,)

    async def deliver(
        self, task: Task, result: ResultLike, *, requested_by: int | None = None
    ) -> DeliveryReport:
        text = (getattr(result, "text", "") or "").strip()
        if not text:
            text = (result.summary or "").strip()
        return await self.deliver_text(task, text, requested_by=requested_by)

    async def deliver_text(
        self, task: Task, text: str, *, requested_by: int | None = None
    ) -> DeliveryReport:
        if not text.strip():
            raise ValueError("risultato vuoto: nessuna consegna")
        sent: list[int] = []
        failed: list[int] = []
        for recipient in self.recipients(task, requested_by=requested_by):
            try:
                await self._notifications.notify([recipient], text)
            except TelegramError as exc:
                failed.append(recipient)
                logger.error(
                    "invio al destinatario fallito",
                    extra={"task_id": task.id, "user_id": recipient, "error": str(exc)},
                )
                continue
            sent.append(recipient)
        logger.info(
            "consegna completata",
            extra={
                "task_id": task.id,
                "sent": len(sent),
                "failed": len(failed),
                "recipients": len(sent) + len(failed),
                "requested_by": requested_by,
            },
        )
        return DeliveryReport(sent=tuple(sent), failed=tuple(failed))
