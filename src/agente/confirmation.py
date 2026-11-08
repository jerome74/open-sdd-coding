"""C-17 Confirmation Flow — riepilogo e conferma esplicita (spec 02, BR-1).

Nessuna modifica diventa effettiva senza conferma dell'amministratore. Le
conferme vivono in memoria nel processo e scadono dopo ``timeout_s`` (piano 02
D5: riuso della soglia BR-3); un riavvio le annulla, il che è fail-safe perché
senza conferma non si scrive nulla (piano 02 A-02).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

logger = logging.getLogger("agente.confirmation")

CONFIRM_PREFIX = "confirm"

AFFIRMATIVE = frozenset(
    {"sì", "si", "sí", "confermo", "approvo", "ok", "yes", "y"}
)
NEGATIVE = frozenset({"no", "annulla", "annullo", "rifiuto", "cancel", "n"})


@dataclass
class _Pending:
    id: str
    requested_by: int
    chat_id: int
    summary: str
    expires_at: datetime
    approved: bool = False
    event: asyncio.Event = field(default_factory=asyncio.Event)


class ConfirmationFlow:
    """Invia il riepilogo, attende la conferma, restituisce l'esito."""

    def __init__(
        self,
        gateway: Any,
        *,
        timeout_s: int = 900,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._gateway = gateway
        self._timeout_s = timeout_s
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex[:12])
        self._pending: dict[str, _Pending] = {}

    async def confirm(self, *, requested_by: int, chat_id: int, summary: str) -> bool:
        """Mostra il riepilogo e attende la conferma entro la scadenza."""
        pending = self._start(requested_by=requested_by, chat_id=chat_id, summary=summary)
        keyboard = (
            (
                ("Conferma", f"{CONFIRM_PREFIX}:{pending.id}:yes"),
                ("Annulla", f"{CONFIRM_PREFIX}:{pending.id}:no"),
            ),
        )
        await self._gateway.send(
            chat_id,
            f"Riepilogo in attesa di conferma\n{summary}\n\n"
            f"Confermi? Rispondi con i bottoni, oppure scrivi «sì» o «no» "
            f"(scade {pending.expires_at.astimezone().strftime('%H:%M')}).",
            keyboard=keyboard,
        )

        remaining = max(0.0, (pending.expires_at - self._clock()).total_seconds())
        try:
            await asyncio.wait_for(pending.event.wait(), timeout=remaining)
        except asyncio.TimeoutError:
            self._pending.pop(pending.id, None)
            logger.info("conferma scaduta", extra={"confirmation_id": pending.id})
            await self._gateway.send(
                chat_id, "Conferma scaduta: nessuna modifica applicata."
            )
            return False

        self._pending.pop(pending.id, None)
        logger.info(
            "conferma risolta",
            extra={"confirmation_id": pending.id, "approved": pending.approved},
        )
        if not pending.approved:
            await self._gateway.send(chat_id, "Operazione annullata.")
        return pending.approved

    def resolve(self, confirmation_id: str, approved: bool, *, by_user_id: int) -> bool:
        """Risolve una conferma in sospeso; solo il richiedente può farlo."""
        pending = self._pending.get(confirmation_id)
        if pending is None:
            logger.info("conferma sconosciuta", extra={"confirmation_id": confirmation_id})
            return False
        if by_user_id != pending.requested_by:
            logger.warning(
                "conferma rifiutata: utente non richiedente",
                extra={"confirmation_id": confirmation_id, "user_id": by_user_id},
            )
            return False
        pending.approved = approved
        pending.event.set()
        return True

    def resolve_text(self, user_id: int, text: str) -> bool:
        """Fallback testuale («sì»/«no») sulla conferma in sospeso dell'utente."""
        keyword = text.strip().lower()
        approved: bool | None = None
        if keyword in AFFIRMATIVE:
            approved = True
        elif keyword in NEGATIVE:
            approved = False
        if approved is None:
            return False
        for pending in self._pending.values():
            if pending.requested_by == user_id and not pending.event.is_set():
                return self.resolve(pending.id, approved, by_user_id=user_id)
        return False

    def pending_for(self, user_id: int) -> str | None:
        for pending in self._pending.values():
            if pending.requested_by == user_id and not pending.event.is_set():
                return pending.id
        return None

    def pending(self) -> list[str]:
        return [pending.id for pending in self._pending.values()]

    def _start(self, *, requested_by: int, chat_id: int, summary: str) -> _Pending:
        pending = _Pending(
            id=self._id_factory(),
            requested_by=requested_by,
            chat_id=chat_id,
            summary=summary,
            expires_at=self._clock() + timedelta(seconds=self._timeout_s),
        )
        self._pending[pending.id] = pending
        return pending
