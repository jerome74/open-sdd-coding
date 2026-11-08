"""C-33 Authorization Notifier — avviso all'admin sui nuovi contatti (spec 08).

Al primo contatto di uno sconosciuto l'amministratore riceve un avviso con il
nome Telegram e il pulsante **Autorizza**. Lo sconosciuto non ottiene alcuna
risposta utile: il rifiuto è inviato da C-14, non da qui.

Anti-spam (D2 del piano 08): al massimo un avviso per utente ogni 24 ore. Il
registro è in memoria: un riavvio può produrre al più un avviso in più, costo
dichiarato e accettato. La finestra avanza solo se l'avviso parte davvero.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from .errors import TelegramError
from .notifications import NotificationService

logger = logging.getLogger("agente.notifier")

AUTHORIZE_PREFIX = "authorize"

# D2: finestra anti-spam per singolo utente sconosciuto.
UNKNOWN_ALERT_WINDOW_S = 24 * 60 * 60


class AuthorizationNotifier:
    def __init__(
        self,
        notifications: NotificationService,
        *,
        clock: Callable[[], datetime] | None = None,
        window_s: int = UNKNOWN_ALERT_WINDOW_S,
    ) -> None:
        self._notifications = notifications
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._window = window_s
        self._last_alert: dict[int, datetime] = {}
        self._names: dict[int, str] = {}

    async def notify_unknown(self, telegram_id: int, username: str | None) -> bool:
        """Avvisa l'admin se la finestra lo consente; ``True`` se l'avviso parte."""
        if username:
            self._names[telegram_id] = username

        now = self._clock()
        last = self._last_alert.get(telegram_id)
        if last is not None and now - last < timedelta(seconds=self._window):
            logger.info(
                "avviso sconosciuto soppresso",
                extra={"telegram_id": telegram_id},
            )
            return False

        text = (
            f"Nuovo contatto: {self._label(telegram_id, username)} "
            f"(id {telegram_id}). Premi «Autorizza» per inviargli "
            "l'informativa privacy."
        )
        keyboard = ((("Autorizza", f"{AUTHORIZE_PREFIX}:{telegram_id}"),),)
        try:
            await self._notifications.alert_admin(text, keyboard=keyboard)
        except TelegramError as exc:
            logger.error(
                "avviso sconosciuto non inviato",
                extra={"telegram_id": telegram_id, "error": str(exc)},
            )
            return False

        self._last_alert[telegram_id] = now
        logger.info("avviso sconosciuto inviato", extra={"telegram_id": telegram_id})
        return True

    def username_for(self, telegram_id: int) -> str | None:
        """Nome Telegram visto nell'ultimo contatto (``None`` dopo un riavvio)."""
        return self._names.get(telegram_id)

    def _label(self, telegram_id: int, username: str | None) -> str:
        name = username or self._names.get(telegram_id)
        return f"@{name}" if name else f"id {telegram_id}"
