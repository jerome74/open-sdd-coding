"""C-17: conferma esplicita, fallback testuale, annullo e scadenza."""

from __future__ import annotations

import asyncio

from agente.confirmation import ConfirmationFlow


class FakeGateway:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []

    async def send(self, chat_id, text, keyboard=None) -> None:
        self.sent.append((chat_id, text, keyboard))


def run(coro):
    return asyncio.run(coro)


def test_confirmation_is_required_before_success() -> None:
    gateway = FakeGateway()
    flow = ConfirmationFlow(gateway, timeout_s=5)

    async def scenario() -> bool:
        async def approve() -> None:
            while not flow.pending():
                await asyncio.sleep(0.01)
            assert flow.resolve(flow.pending()[0], True, by_user_id=1)

        result, _ = await asyncio.gather(
            flow.confirm(requested_by=1, chat_id=1, summary="Nuovo compito: rassegna"),
            approve(),
        )
        return result

    assert run(scenario()) is True
    chat_id, text, keyboard = gateway.sent[0]
    assert chat_id == 1
    assert "Nuovo compito: rassegna" in text
    assert any("confirm:" in data for row in keyboard for _, data in row)


def test_rejection_announces_cancellation() -> None:
    gateway = FakeGateway()
    flow = ConfirmationFlow(gateway, timeout_s=5)

    async def scenario() -> bool:
        async def reject() -> None:
            while not flow.pending():
                await asyncio.sleep(0.01)
            assert flow.resolve(flow.pending()[0], False, by_user_id=1)

        result, _ = await asyncio.gather(
            flow.confirm(requested_by=1, chat_id=1, summary="elimina compito"),
            reject(),
        )
        return result

    assert run(scenario()) is False
    assert "Operazione annullata." in gateway.sent[-1][1]


def test_timeout_cancels_with_message() -> None:
    gateway = FakeGateway()
    flow = ConfirmationFlow(gateway, timeout_s=0)
    assert run(flow.confirm(requested_by=1, chat_id=1, summary="riepilogo")) is False
    assert "Conferma scaduta" in gateway.sent[-1][1]
    assert flow.pending() == []


def test_only_requesting_admin_can_resolve() -> None:
    gateway = FakeGateway()
    flow = ConfirmationFlow(gateway, timeout_s=5)

    async def scenario() -> tuple[bool, bool, bool]:
        async def act() -> tuple[bool, bool, bool]:
            while not flow.pending():
                await asyncio.sleep(0.01)
            confirmation_id = flow.pending()[0]
            wrong = flow.resolve(confirmation_id, True, by_user_id=99)
            right = flow.resolve(confirmation_id, True, by_user_id=1)
            return wrong, right, flow.pending_for(1) is None

        result, flags = await asyncio.gather(
            flow.confirm(requested_by=1, chat_id=1, summary="riepilogo"),
            act(),
        )
        assert result is True
        return flags

    wrong, right, cleared = run(scenario())
    assert (wrong, right, cleared) == (False, True, True)


def test_text_fallback_resolves_pending() -> None:
    gateway = FakeGateway()
    flow = ConfirmationFlow(gateway, timeout_s=5)

    async def scenario() -> bool:
        async def answer() -> None:
            while not flow.pending_for(1):
                await asyncio.sleep(0.01)
            assert flow.resolve_text(1, "sì")

        result, _ = await asyncio.gather(
            flow.confirm(requested_by=1, chat_id=1, summary="riepilogo"),
            answer(),
        )
        return result

    assert run(scenario()) is True


def test_text_fallback_ignores_other_users_and_unknown_words() -> None:
    gateway = FakeGateway()
    flow = ConfirmationFlow(gateway, timeout_s=0)

    async def scenario() -> None:
        await flow.confirm(requested_by=1, chat_id=1, summary="riepilogo")

    run(scenario())
    assert flow.resolve_text(2, "sì") is False
    assert flow.resolve_text(1, "forse") is False
