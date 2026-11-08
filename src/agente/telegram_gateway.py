"""C-03 Telegram Gateway — long polling, invio, inline keyboard.

Telegram è incapsulato qui: nessun altro modulo importa la libreria.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .errors import TelegramError
from .notifications import split_message
from .retry import async_retry_call

logger = logging.getLogger("agente.telegram")

Keyboard = Sequence[Sequence[tuple[str, str]]]
AsyncSleep = Callable[[float], Any]
InboundHandler = Callable[["IncomingMessage"], Any]


@dataclass(frozen=True)
class IncomingMessage:
    """Messaggio in ingresso normalizzato: C-03 non espone la libreria.

    ``callback_data`` è valorizzato per i bottoni inline (conferme); ``text``
    resta vuoto in quel caso. ``username`` è il nome Telegram del mittente
    (spec 08): serve a C-33 per l'avviso all'amministratore.
    """

    user_id: int
    chat_id: int
    text: str = ""
    callback_data: str | None = None
    username: str | None = None


class _RetryableTelegram(Exception):
    """Errore di rete/rate limit: ritentabile secondo BR-8."""


class TelegramGateway:
    def __init__(
        self,
        token: str,
        *,
        application: Any | None = None,
        retry_attempts: int = 3,
        retry_delay_s: float = 60.0,
        sleep: AsyncSleep = asyncio.sleep,
    ) -> None:
        self._token = token
        self._app = application
        self._retry_attempts = retry_attempts
        self._retry_delay_s = retry_delay_s
        self._sleep = sleep
        self._handlers: list[tuple[Any, int]] = []
        self._inbound: InboundHandler | None = None
        self._inbound_registered = False
        self._tasks: set[asyncio.Task[Any]] = set()

    def add_handler(self, handler: Any, group: int = 0) -> None:
        self._handlers.append((handler, group))
        if self._app is not None:
            self._app.add_handler(handler, group=group)

    def set_inbound_handler(self, handler: InboundHandler | None) -> None:
        """Registra il consumatore dei messaggi in ingresso (C-14)."""
        self._inbound = handler
        self._inbound_registered = False
        self._register_inbound()

    async def start(self) -> None:
        if self._app is None:
            from telegram.ext import Application  # import locale: solo runtime reale

            self._app = Application.builder().token(self._token).build()
            for handler, group in self._handlers:
                self._app.add_handler(handler, group=group)
        self._register_inbound()
        await self._app.initialize()
        await self._app.start()
        updater = getattr(self._app, "updater", None)
        if updater is not None:
            await updater.start_polling()
        logger.info("gateway Telegram avviato in long polling")

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
        if self._app is None:
            return
        updater = getattr(self._app, "updater", None)
        if updater is not None:
            await updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        logger.info("gateway Telegram fermato")

    def _register_inbound(self) -> None:
        """Collega i messaggi e i bottoni al consumatore applicativo (C-14)."""
        if self._inbound is None or self._inbound_registered or self._app is None:
            return
        from telegram.ext import CallbackQueryHandler, MessageHandler, filters

        self._app.add_handler(MessageHandler(filters.COMMAND, self._on_message))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )
        self._app.add_handler(CallbackQueryHandler(self._on_callback))
        self._inbound_registered = True

    async def _on_message(self, update: Any, context: Any) -> None:
        message = getattr(update, "effective_message", None)
        user = getattr(update, "effective_user", None)
        if message is None or user is None:
            return
        chat = getattr(message, "chat", None)
        self._dispatch(
            IncomingMessage(
                user_id=int(user.id),
                chat_id=int(getattr(chat, "id", user.id)),
                text=str(getattr(message, "text", "") or ""),
                username=_username(user),
            )
        )

    async def _on_callback(self, update: Any, context: Any) -> None:
        query = getattr(update, "callback_query", None)
        if query is None:
            return
        try:
            await query.answer()
        except Exception:  # noqa: BLE001 - la risposta al bottone è best effort
            logger.warning("risposta al bottone non inviata")
        user = getattr(query, "from_user", None)
        message = getattr(query, "message", None)
        chat = getattr(message, "chat", None)
        if user is None:
            return
        self._dispatch(
            IncomingMessage(
                user_id=int(user.id),
                chat_id=int(getattr(chat, "id", user.id)),
                callback_data=str(getattr(query, "data", "") or ""),
                username=_username(user),
            )
        )

    def _dispatch(self, incoming: IncomingMessage) -> None:
        """Esegue il consumatore in background: un'attesa di conferma non blocca
        il polling (il bottone che la risolve deve poter arrivare)."""
        if self._inbound is None:
            return
        task = asyncio.create_task(self._run_inbound(incoming))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_inbound(self, incoming: IncomingMessage) -> None:
        assert self._inbound is not None
        try:
            await self._inbound(incoming)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - un update guasto non ferma il polling
            logger.exception("errore nella gestione del messaggio in ingresso")

    async def send(
        self,
        chat_id: int,
        text: str,
        keyboard: Keyboard | None = None,
    ) -> int | None:
        """Invia il testo (spezzato se serve) e restituisce l'id dell'ultimo pezzo.

        L'id serve a C-25 per rimuovere l'indicatore di avanzamento (spec 05);
        i chiamanti che non lo usano possono ignorarlo.
        """
        chunks = split_message(text)
        last_id: int | None = None
        for index, chunk in enumerate(chunks):
            markup = _markup(keyboard) if keyboard and index == len(chunks) - 1 else None
            last_id = await self._send_chunk(chat_id, chunk, markup)
        return last_id

    async def _send_chunk(self, chat_id: int, text: str, markup: Any) -> int | None:
        if self._app is None:
            raise TelegramError("gateway non avviato")

        async def attempt() -> Any:
            try:
                return await self._app.bot.send_message(
                    chat_id=chat_id, text=text, reply_markup=markup
                )
            except Exception as exc:  # noqa: BLE001 - classificato subito
                if _is_retryable(exc):
                    raise _RetryableTelegram(type(exc).__name__) from exc
                raise TelegramError(f"invio Telegram rifiutato: {exc}") from exc

        try:
            message = await async_retry_call(
                attempt,
                attempts=self._retry_attempts,
                delay_s=self._retry_delay_s,
                retry_on=(_RetryableTelegram,),
                sleep=self._sleep,
            )
        except _RetryableTelegram as exc:
            logger.error("invio Telegram fallito dopo i retry")
            raise TelegramError(f"invio Telegram fallito: {exc}") from exc
        logger.info("messaggio inviato", extra={"chat_id": chat_id, "chars": len(text)})
        message_id = getattr(message, "message_id", None)
        return message_id if isinstance(message_id, int) else None

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        """Cancella un messaggio già inviato (indicatore di avanzamento C-25)."""
        if self._app is None:
            raise TelegramError("gateway non avviato")

        async def attempt() -> Any:
            try:
                return await self._app.bot.delete_message(
                    chat_id=chat_id, message_id=message_id
                )
            except Exception as exc:  # noqa: BLE001 - classificato subito
                if _is_retryable(exc):
                    raise _RetryableTelegram(type(exc).__name__) from exc
                raise TelegramError(f"cancellazione Telegram rifiutata: {exc}") from exc

        try:
            await async_retry_call(
                attempt,
                attempts=self._retry_attempts,
                delay_s=self._retry_delay_s,
                retry_on=(_RetryableTelegram,),
                sleep=self._sleep,
            )
        except _RetryableTelegram as exc:
            logger.error("cancellazione Telegram fallita dopo i retry")
            raise TelegramError(f"cancellazione Telegram fallita: {exc}") from exc
        logger.info(
            "messaggio eliminato",
            extra={"chat_id": chat_id, "message_id": message_id},
        )


def _username(user: Any) -> str | None:
    value = getattr(user, "username", None)
    return value if isinstance(value, str) and value else None


def _markup(keyboard: Keyboard) -> Any:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [InlineKeyboardButton(label, callback_data=data) for label, data in row]
        for row in keyboard
    ]
    return InlineKeyboardMarkup(rows)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, OSError)):
        return True
    try:
        from telegram.error import NetworkError, RetryAfter, TimedOut

        return isinstance(exc, (NetworkError, RetryAfter, TimedOut))
    except Exception:  # noqa: BLE001 - libreria assente o diversa
        return type(exc).__name__ in {"NetworkError", "RetryAfter", "TimedOut"}
