"""C-03: invio, split, inline keyboard, retry (AC-04 ramo Telegram)."""

from __future__ import annotations

import asyncio

import pytest

from agente.errors import TelegramError
from agente.telegram_gateway import TelegramGateway


class _SentMessage:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


class FakeBot:
    def __init__(self, failures: int = 0, error: Exception | None = None) -> None:
        self.failures = failures
        self.error = error
        self.calls: list[dict] = []
        self.deleted: list[tuple[int, int]] = []
        self.delete_error: Exception | None = None
        self._next_id = 0

    async def send_message(self, chat_id, text, reply_markup=None):
        self.calls.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )
        if self.error is not None:
            raise self.error
        if self.failures:
            self.failures -= 1
            raise TimeoutError("rete")
        self._next_id += 1
        return _SentMessage(self._next_id)

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))
        if self.delete_error is not None:
            raise self.delete_error


class FakeUpdater:
    def __init__(self) -> None:
        self.polling = False
        self.stopped = False

    async def start_polling(self) -> None:
        self.polling = True

    async def stop(self) -> None:
        self.stopped = True


class FakeApp:
    def __init__(self, bot: FakeBot) -> None:
        self.bot = bot
        self.updater = FakeUpdater()
        self.initialized = False
        self.started = False
        self.stopped = False
        self.shutdown_called = False
        self.handlers: list[object] = []

    def add_handler(self, handler, group: int = 0) -> None:
        self.handlers.append(handler)

    async def initialize(self) -> None:
        self.initialized = True

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def shutdown(self) -> None:
        self.shutdown_called = True


def test_start_and_stop_manage_polling() -> None:
    app = FakeApp(FakeBot())
    gateway = TelegramGateway("token", application=app)
    handler = object()
    gateway.add_handler(handler)

    asyncio.run(gateway.start())
    assert app.initialized is True
    assert app.started is True
    assert app.updater.polling is True
    assert app.handlers == [handler]

    asyncio.run(gateway.stop())
    assert app.updater.stopped is True
    assert app.stopped is True
    assert app.shutdown_called is True


def test_send_splits_long_text_and_attaches_keyboard_last() -> None:
    bot = FakeBot()
    gateway = TelegramGateway("token", application=FakeApp(bot))

    asyncio.run(
        gateway.send(7, "a" * 5000, keyboard=((("Approva", "approval:1:approve"),),))
    )

    assert len(bot.calls) == 2
    assert bot.calls[0]["reply_markup"] is None
    markup = bot.calls[-1]["reply_markup"]
    assert markup.inline_keyboard[0][0].text == "Approva"
    assert markup.inline_keyboard[0][0].callback_data == "approval:1:approve"


def test_retry_three_times_on_transient_error() -> None:
    bot = FakeBot(failures=2)
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    gateway = TelegramGateway("token", application=FakeApp(bot), sleep=fake_sleep)
    asyncio.run(gateway.send(7, "ciao"))

    assert len(bot.calls) == 3
    assert sleeps == [60, 60]


def test_permanent_error_is_not_retried() -> None:
    bot = FakeBot(error=ValueError("chat non valida"))
    gateway = TelegramGateway("token", application=FakeApp(bot))

    with pytest.raises(TelegramError):
        asyncio.run(gateway.send(7, "ciao"))
    assert len(bot.calls) == 1


class FakeUser:
    id = 2


class FakeChat:
    id = 22


class FakeMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.chat = FakeChat()


class FakeUpdate:
    def __init__(self, text: str = "", user=None) -> None:
        self.effective_message = FakeMessage(text)
        self.effective_user = user or FakeUser()


class FakeQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = FakeUser()
        self.message = FakeMessage()
        self.answered = False

    async def answer(self) -> None:
        self.answered = True


class FakeCallbackUpdate:
    def __init__(self, data: str) -> None:
        self.callback_query = FakeQuery(data)


def test_inbound_text_message_is_normalised_to_the_application() -> None:
    app = FakeApp(FakeBot())
    gateway = TelegramGateway("token", application=app)
    received: list[object] = []

    async def handler(incoming) -> None:
        received.append(incoming)

    async def scenario() -> None:
        gateway.set_inbound_handler(handler)
        await gateway.start()
        await gateway._on_message(FakeUpdate("/pause rassegna"), None)
        await asyncio.sleep(0.01)
        await gateway.stop()

    asyncio.run(scenario())
    assert len(received) == 1
    incoming = received[0]
    assert (incoming.user_id, incoming.chat_id, incoming.text) == (2, 22, "/pause rassegna")
    assert incoming.callback_data is None


def test_inbound_callback_is_answered_and_dispatched() -> None:
    app = FakeApp(FakeBot())
    gateway = TelegramGateway("token", application=app)
    received: list[object] = []
    update = FakeCallbackUpdate("confirm:abc:yes")

    async def handler(incoming) -> None:
        received.append(incoming)

    async def scenario() -> None:
        gateway.set_inbound_handler(handler)
        await gateway.start()
        await gateway._on_callback(update, None)
        await asyncio.sleep(0.01)
        await gateway.stop()

    asyncio.run(scenario())
    assert update.callback_query.answered is True
    assert received[0].callback_data == "confirm:abc:yes"
    assert received[0].text == ""


def test_inbound_errors_do_not_escape() -> None:
    app = FakeApp(FakeBot())
    gateway = TelegramGateway("token", application=app)

    async def handler(incoming) -> None:
        raise RuntimeError("boom")

    async def scenario() -> None:
        gateway.set_inbound_handler(handler)
        await gateway.start()
        await gateway._on_message(FakeUpdate("ciao"), None)
        await asyncio.sleep(0.01)
        await gateway.stop()

    asyncio.run(scenario())


def test_send_returns_the_last_message_id() -> None:
    bot = FakeBot()
    gateway = TelegramGateway("token", application=FakeApp(bot))

    assert asyncio.run(gateway.send(7, "ciao")) == 1


def test_delete_message_uses_the_bot() -> None:
    bot = FakeBot()
    gateway = TelegramGateway("token", application=FakeApp(bot))

    asyncio.run(gateway.delete_message(7, 42))

    assert bot.deleted == [(7, 42)]


def test_delete_message_failure_raises_telegram_error() -> None:
    bot = FakeBot()
    bot.delete_error = ValueError("non trovato")
    gateway = TelegramGateway("token", application=FakeApp(bot))

    with pytest.raises(TelegramError):
        asyncio.run(gateway.delete_message(7, 42))


class FakeNamedUser:
    id = 5
    username = "mario"


class FakeNamedQuery(FakeQuery):
    def __init__(self, data: str) -> None:
        super().__init__(data)
        self.from_user = FakeNamedUser()

    @property
    def callback_query(self):  # pragma: no cover - non usato
        raise AssertionError


def test_username_is_carried_in_the_incoming_message() -> None:
    app = FakeApp(FakeBot())
    gateway = TelegramGateway("token", application=app)
    received: list[object] = []

    async def handler(incoming) -> None:
        received.append(incoming)

    async def scenario() -> None:
        gateway.set_inbound_handler(handler)
        await gateway.start()
        await gateway._on_message(FakeUpdate("ciao", user=FakeNamedUser()), None)
        await asyncio.sleep(0.01)
        await gateway.stop()

    asyncio.run(scenario())
    assert received[0].username == "mario"


def test_username_is_carried_in_callback_messages() -> None:
    app = FakeApp(FakeBot())
    gateway = TelegramGateway("token", application=app)
    received: list[object] = []

    async def handler(incoming) -> None:
        received.append(incoming)

    class NamedCallbackUpdate:
        callback_query = FakeNamedQuery("consent:accept")

    async def scenario() -> None:
        gateway.set_inbound_handler(handler)
        await gateway.start()
        await gateway._on_callback(NamedCallbackUpdate(), None)
        await asyncio.sleep(0.01)
        await gateway.stop()

    asyncio.run(scenario())
    assert received[0].username == "mario"
    assert received[0].callback_data == "consent:accept"
