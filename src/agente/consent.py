"""C-32 Consent Flow — informativa privacy e accettazione (spec 08, BR-18).

Regole applicate qui, non delegate al modello:

- l'informativa si invia solo a chi è stato autorizzato dall'amministratore;
- l'utente passa a ``accepted`` **solo** dopo un'accettazione esplicita; un
  rifiuto lo porta a ``revoked`` e avvisa l'amministratore;
- solo il destinatario può accettare o rifiutare al posto proprio;
- il tetto BR-16 è applicato nell'istante in cui lo stato diventerebbe
  ``accepted``, non alla sola creazione del record.

Il testo è quello fornito dall'operatore (D1 del piano 08, A-02 della spec) e
non viene modificato a runtime: nessuna chiave di configurazione nuova.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from .errors import TelegramError, UserAccessError
from .notifications import NotificationService
from .storage.repositories import User, UserRepository
from .user_state import MAX_AUTHORIZED_USERS, UserResult

logger = logging.getLogger("agente.consent")

CONSENT_PREFIX = "consent"

# D1 (2026-11-01): testo approvato dall'operatore. Una modifica è un cambio di
# codice + documento, non un valore di configurazione.
PRIVACY_NOTICE = (
    "Privacy — come funziona l'agente. I tuoi messaggi a questo bot passano dai "
    "server di DeepSeek (per generare le risposte) e di Telegram (per il "
    "trasporto). Sono conservati nella memoria dell'agente sul telefono (S24) "
    "dell'amministratore e l'amministratore può rileggerli. Puoi chiedere in ogni "
    "momento all'amministratore di revocare il tuo accesso. Premi «Accetto» per "
    "usare l'agente; «Rifiuto» per non autorizzare l'accesso."
)

_CONSENT_KEYBOARD = (
    (("Accetto", f"{CONSENT_PREFIX}:accept"), ("Rifiuto", f"{CONSENT_PREFIX}:decline")),
)


class ConsentFlow:
    def __init__(
        self,
        users: UserRepository,
        notifications: NotificationService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._users = users
        self._notifications = notifications
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def send_consent(self, user_id: int) -> bool:
        """Invia l'informativa con i bottoni; ``False`` se l'invio fallisce."""
        try:
            await self._notifications.notify(
                [user_id], PRIVACY_NOTICE, keyboard=_CONSENT_KEYBOARD
            )
        except TelegramError as exc:
            logger.error(
                "informativa privacy non inviata",
                extra={"user_id": user_id, "error": str(exc)},
            )
            await self._alert(
                f"Informativa privacy non inviata all'utente {user_id}: {exc}"
            )
            return False
        logger.info("informativa privacy inviata", extra={"user_id": user_id})
        return True

    async def accept(self, user_id: int, *, by_user_id: int) -> UserResult:
        """Registra l'accettazione esplicita e abilita l'utente (BR-18)."""
        user = self._require_user(user_id)
        self._require_self(user_id, by_user_id)
        if user.state != "pending":
            raise UserAccessError(
                f"accettazione non ammessa nello stato {user.state}",
                reason="invalid_state",
            )
        if self._accepted_count() >= MAX_AUTHORIZED_USERS:
            await self._alert(
                f"Limite di {MAX_AUTHORIZED_USERS} utenti autorizzati raggiunto: "
                f"l'utente {user_id} non è stato abilitato."
            )
            raise UserAccessError(
                f"limite di {MAX_AUTHORIZED_USERS} utenti autorizzati raggiunto",
                reason="limit",
            )

        self._users.set_state(user_id, "accepted")
        self._users.set_consent(user_id, self._now())
        updated = self._require_user(user_id)
        logger.info("informativa accettata", extra={"user_id": user_id})
        return UserResult(
            user=updated,
            changed=True,
            note="Hai accettato l'informativa: ora sei autorizzato.",
        )

    async def decline(self, user_id: int, *, by_user_id: int) -> UserResult:
        """Registra il rifiuto, lascia l'utente non autorizzato e avvisa l'admin."""
        user = self._require_user(user_id)
        self._require_self(user_id, by_user_id)
        if user.state != "pending":
            raise UserAccessError(
                f"rifiuto non ammesso nello stato {user.state}",
                reason="invalid_state",
            )

        self._users.set_state(user_id, "revoked")
        updated = self._require_user(user_id)
        logger.info("informativa rifiutata", extra={"user_id": user_id})
        await self._alert(
            f"L'utente {_label(updated)} (id {user_id}) ha rifiutato l'informativa "
            "privacy: resta non autorizzato."
        )
        return UserResult(
            user=updated,
            changed=True,
            note="Hai rifiutato l'informativa: resti non autorizzato.",
        )

    # --- interni ----------------------------------------------------------

    def _require_user(self, user_id: int) -> User:
        user = self._users.get(user_id)
        if user is None:
            raise UserAccessError(f"utente non trovato: {user_id}", reason="not_found")
        return user

    def _require_self(self, user_id: int, by_user_id: int) -> None:
        if by_user_id != user_id:
            raise UserAccessError(
                "solo il destinatario può accettare o rifiutare",
                reason="invalid_target",
            )

    def _accepted_count(self) -> int:
        return len(self._users.list("accepted"))

    def _now(self) -> str:
        return self._clock().isoformat(timespec="seconds")

    async def _alert(self, text: str) -> None:
        """Avviso all'admin best effort: un invio fallito non cambia lo stato."""
        try:
            await self._notifications.alert_admin(text)
        except TelegramError as exc:
            logger.error("avviso all'admin non inviato", extra={"error": str(exc)})


def _label(user: User) -> str:
    return f"@{user.username}" if user.username else f"id {user.telegram_id}"


__all__ = [
    "CONSENT_PREFIX",
    "PRIVACY_NOTICE",
    "ConsentFlow",
]
