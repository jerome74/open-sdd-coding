"""C-25: soglia, indicator, cancellazione e generazione (spec 05, D5)."""

from __future__ import annotations

import asyncio

from agente.errors import TelegramError
from agente.progress import DEFAULT_TEXT, ProgressIndicator


class FakeGateway:
    def __init__(self, *, fail_send: bool = False, fail_delete: bool = False) -> None:
        self.sent: list[tuple[int, str]] = []
        self.deleted: list[tuple[int, int]] = []
        self.fail_send = fail_send
        self.fail_delete = fail_delete
        self._next_id = 10

    async def send(self, chat_id: int, text: str) -> int:
        if self.fail_send:
            raise TelegramError("invio rifiutato")
        self._next_id += 1
        self.sent.append((chat_id, text))
        return self._next_id

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        if self.fail_delete:
            raise TelegramError("cancellazione rifiutata")
        self.deleted.append((chat_id, message_id))


def test_indicator_is_not_sent_below_the_threshold() -> None:
    gateway = FakeGateway()
    indicator = ProgressIndicator(gateway, threshold_s=1.0)

    async def scenario() -> None:
        await indicator.start(7)
        await indicator.finish(7)

    asyncio.run(scenario())

    assert gateway.sent == []
    assert gateway.deleted == []


def test_indicator_is_sent_after_the_threshold_and_removed() -> None:
    gateway = FakeGateway()
    indicator = ProgressIndicator(gateway, threshold_s=0.01)

    async def scenario() -> None:
        await indicator.start(7)
        await asyncio.sleep(0.05)
        assert gateway.sent == [(7, DEFAULT_TEXT)]
        await indicator.finish(7)

    asyncio.run(scenario())

    assert gateway.deleted == [(7, 11)]


def test_finish_before_the_threshold_cancels_the_timer() -> None:
    gateway = FakeGateway()
    indicator = ProgressIndicator(gateway, threshold_s=0.2)

    async def scenario() -> None:
        await indicator.start(7)
        await indicator.finish(7)
        await asyncio.sleep(0.25)

    asyncio.run(scenario())

    assert gateway.sent == []


def test_new_request_closes_the_previous_indicator() -> None:
    gateway = FakeGateway()
    indicator = ProgressIndicator(gateway, threshold_s=0.01)

    async def scenario() -> None:
        await indicator.start(7)
        await asyncio.sleep(0.05)  # primo indicatore inviato
        await indicator.start(7)  # chiude il primo e apre il secondo
        await asyncio.sleep(0.05)  # secondo indicatore inviato
        await indicator.finish(7)

    asyncio.run(scenario())

    assert len(gateway.sent) == 2
    # Il nuovo start chiude l'indicatore vecchio; il finish cancella il corrente.
    assert gateway.deleted == [(7, 11), (7, 12)]


def test_send_failure_does_not_break_the_response() -> None:
    gateway = FakeGateway(fail_send=True)
    indicator = ProgressIndicator(gateway, threshold_s=0.01)

    async def scenario() -> None:
        await indicator.start(7)
        await asyncio.sleep(0.05)
        await indicator.finish(7)

    asyncio.run(scenario())

    assert gateway.sent == []
    assert gateway.deleted == []


def test_delete_failure_does_not_propagate() -> None:
    gateway = FakeGateway(fail_delete=True)
    indicator = ProgressIndicator(gateway, threshold_s=0.01)

    async def scenario() -> None:
        await indicator.start(7)
        await asyncio.sleep(0.05)
        await indicator.finish(7)

    asyncio.run(scenario())

    assert gateway.deleted == []


def test_finish_without_start_is_a_noop() -> None:
    gateway = FakeGateway()
    indicator = ProgressIndicator(gateway, threshold_s=0.01)

    asyncio.run(indicator.finish(7))

    assert gateway.sent == []


class SlowDeleteGateway(FakeGateway):
    def __init__(self, delay: float) -> None:
        super().__init__()
        self.delay = delay

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        await asyncio.sleep(self.delay)
        await super().delete_message(chat_id, message_id)


def test_finish_does_not_wait_for_a_slow_delete() -> None:
    """P-A-12: la cancellazione non deve ritardare la risposta (retry BR-8)."""
    gateway = SlowDeleteGateway(delay=0.2)
    indicator = ProgressIndicator(gateway, threshold_s=0.01)

    async def scenario() -> float:
        await indicator.start(7)
        await asyncio.sleep(0.05)
        started = asyncio.get_running_loop().time()
        await indicator.finish(7)
        elapsed = asyncio.get_running_loop().time() - started
        await asyncio.sleep(0.25)  # lascia completare la cancellazione
        return elapsed

    elapsed = asyncio.run(scenario())

    assert elapsed < 0.1
    assert gateway.deleted == [(7, 11)]
