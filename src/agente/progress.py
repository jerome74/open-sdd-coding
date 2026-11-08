"""C-25 Progress Indicator — «sto cercando…» durante l'attesa (spec 05).

Dopo ``threshold_s`` secondi (``limits.chat_progress_s``, decisione D5) invia un
messaggio di attesa; alla risposta lo elimina. Invio e cancellazione passano da
C-03 e sono best effort: un errore non blocca la risposta (requisito di spec 05).

Lo stato è per ``chat_id`` e porta un contatore di generazione: se una richiesta
successiva parte prima che la precedente finisca, il ``finish`` vecchio non
cancella l'indicatore nuovo. Se ``finish`` arriva prima dello scatto, il timer
viene annullato e nessun indicatore compare.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .errors import TelegramError

logger = logging.getLogger("agente.progress")

DEFAULT_TEXT = "sto cercando…"

Sleep = Callable[[float], Awaitable[Any]]


@dataclass
class _State:
    generation: int
    task: asyncio.Task[Any] | None = None
    message_id: int | None = None
    finished: bool = False


class ProgressIndicator:
    def __init__(
        self,
        gateway: Any,
        *,
        threshold_s: float,
        text: str = DEFAULT_TEXT,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._gateway = gateway
        self._threshold_s = threshold_s
        self._text = text
        self._sleep = sleep
        self._generation = 0
        self._states: dict[int, _State] = {}
        self._deletions: set[asyncio.Task[Any]] = set()

    async def start(self, chat_id: int) -> None:
        """Avvia il timer della soglia; non attende l'invio."""
        previous = self._states.get(chat_id)
        if previous is not None:
            await self._finish_state(chat_id, previous)
        self._generation += 1
        state = _State(generation=self._generation)
        self._states[chat_id] = state
        state.task = asyncio.create_task(self._show_later(chat_id, state))

    async def finish(self, chat_id: int) -> None:
        """Annulla il timer o elimina l'indicatore già inviato."""
        state = self._states.pop(chat_id, None)
        if state is None:
            return
        await self._finish_state(chat_id, state)

    # --- interni ----------------------------------------------------------

    async def _finish_state(self, chat_id: int, state: _State) -> None:
        state.finished = True
        task = state.task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if state.message_id is None:
            return
        # La cancellazione è best effort e non deve ritardare la risposta: i
        # retry BR-8 di C-03 possono durare fino a due minuti (P-A-12).
        deletion = asyncio.create_task(self._delete(chat_id, state.message_id))
        self._deletions.add(deletion)
        deletion.add_done_callback(self._deletions.discard)
        # Un solo giro di loop: la cancellazione parte, la risposta prosegue.
        await asyncio.sleep(0)

    async def _delete(self, chat_id: int, message_id: int) -> None:
        try:
            await self._gateway.delete_message(chat_id, message_id)
        except TelegramError as exc:
            logger.warning(
                "indicatore non rimosso",
                extra={"chat_id": chat_id, "error": str(exc)},
            )

    async def _show_later(self, chat_id: int, state: _State) -> None:
        try:
            await self._sleep(self._threshold_s)
        except asyncio.CancelledError:
            raise
        if state.finished or self._states.get(chat_id) is not state:
            return
        try:
            message_id = await self._gateway.send(chat_id, self._text)
        except TelegramError as exc:
            # Requisito di spec 05: l'indicatore non blocca la risposta.
            logger.warning(
                "indicatore non inviato",
                extra={"chat_id": chat_id, "error": str(exc)},
            )
            return
        if isinstance(message_id, int):
            state.message_id = message_id
            logger.info("indicatore inviato", extra={"chat_id": chat_id})
        else:
            # C-03 non ha restituito l'id: il messaggio resta senza possibilità
            # di cancellazione (best effort), ma il fatto viene registrato.
            logger.warning("indicatore senza id: nessuna cancellazione")
