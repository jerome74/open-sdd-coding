"""C-28: creazione, invio, timeout, ruoli, riavvio e cancellazione (spec 06)."""

from __future__ import annotations

import asyncio
import logging
import pytest

from agente.approvals import ApprovalManager
from agente.errors import TelegramError
from agente.notifications import NotificationService
from agente.role_guard import RoleGuard
from agente.storage.db import Database
from agente.storage.repositories import Approval, User, repositories
from conftest import ADMIN_ID, USER_ID


class FakeGateway:
    def __init__(self, *, fail: bool = False, delay: float = 0.0) -> None:
        self.sent: list[tuple[int, str, object]] = []
        self.fail = fail
        self.delay = delay

    async def send(self, chat_id, text, keyboard=None) -> int:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise TelegramError("invio rifiutato")
        self.sent.append((chat_id, text, keyboard))
        return len(self.sent)


@pytest.fixture
def env(tmp_path, make_config):
    db = Database(tmp_path / "approvals.db")
    db.migrate()
    repos = repositories(db.connection)
    config = make_config(admin_id=ADMIN_ID)
    repos.users.upsert(User(telegram_id=USER_ID, username="utente", state="accepted"))
    roles = RoleGuard(config, repos.users)

    def build(*, timeout_s: float = 5.0, gateway=None, fail: bool = False):
        channel = gateway or FakeGateway(fail=fail)
        notifications = NotificationService(channel, config, repos.approvals)
        manager = ApprovalManager(
            repos.approvals,
            notifications,
            roles,
            timeout_s=timeout_s,
        )
        return manager, channel, repos

    yield build
    db.close()


async def _wait_for_request(channel: FakeGateway, manager) -> None:
    for _ in range(100):
        if channel.sent:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("richiesta non inviata")


def test_request_goes_to_the_admin_with_buttons(env) -> None:
    manager, channel, repos = env()

    async def scenario():
        pending = asyncio.create_task(
            manager.request(action="delete_file", reason="pulizia", requester=USER_ID)
        )
        await _wait_for_request(channel, manager)
        chat_id, text, keyboard = channel.sent[0]
        assert chat_id == ADMIN_ID
        assert "delete_file" in text and "pulizia" in text
        assert keyboard[0][0][0] == "Approva"
        assert keyboard[0][1][0] == "Rifiuta"
        approval_id = int(keyboard[0][0][1].split(":")[1])
        assert manager.resolve(approval_id, "approved", by_user_id=ADMIN_ID)
        return await pending

    approval = asyncio.run(scenario())

    assert approval.status == "approved"
    assert repos.approvals.get(approval.id).status == "approved"


def test_rejection_is_returned_and_no_action_is_authorized(env) -> None:
    manager, channel, _repos = env()

    async def scenario():
        pending = asyncio.create_task(
            manager.request(action="run_command", reason="rm", requester=USER_ID)
        )
        await _wait_for_request(channel, manager)
        approval_id = int(channel.sent[0][2][0][0][1].split(":")[1])
        assert manager.resolve(approval_id, "rejected", by_user_id=ADMIN_ID)
        return await pending

    approval = asyncio.run(scenario())

    assert approval.status == "rejected"
    assert manager.is_executable(approval) is False


def test_timeout_marks_the_request_rejected(env) -> None:
    manager, _channel, repos = env(timeout_s=0.05)

    approval = asyncio.run(
        manager.request(action="delete_file", reason="pulizia", requester=USER_ID)
    )

    assert approval.status == "rejected"
    assert repos.approvals.get(approval.id).status == "rejected"
    assert manager.is_executable(approval) is False


def test_only_the_admin_can_resolve(env) -> None:
    manager, channel, repos = env()

    async def scenario():
        pending = asyncio.create_task(
            manager.request(action="delete_file", reason="pulizia", requester=USER_ID)
        )
        await _wait_for_request(channel, manager)
        approval_id = int(channel.sent[0][2][0][0][1].split(":")[1])
        assert manager.resolve(approval_id, "approved", by_user_id=USER_ID) is False
        assert repos.approvals.get(approval_id).status == "pending"
        manager.resolve(approval_id, "rejected", by_user_id=ADMIN_ID)
        return await pending

    assert asyncio.run(scenario()).status == "rejected"


def test_double_resolution_is_rejected(env) -> None:
    manager, channel, _repos = env()

    async def scenario():
        pending = asyncio.create_task(
            manager.request(action="delete_file", reason="pulizia", requester=USER_ID)
        )
        await _wait_for_request(channel, manager)
        approval_id = int(channel.sent[0][2][0][0][1].split(":")[1])
        assert manager.resolve(approval_id, "approved", by_user_id=ADMIN_ID)
        assert manager.resolve(approval_id, "rejected", by_user_id=ADMIN_ID) is False
        await pending

    asyncio.run(scenario())


def test_cancelled_wait_marks_rejected(env) -> None:
    manager, channel, repos = env()

    async def scenario() -> int:
        pending = asyncio.create_task(
            manager.request(action="delete_file", reason="pulizia", requester=USER_ID)
        )
        await _wait_for_request(channel, manager)
        approval_id = int(channel.sent[0][2][0][0][1].split(":")[1])
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        return approval_id

    approval_id = asyncio.run(scenario())

    assert repos.approvals.get(approval_id).status == "rejected"


def test_cancelled_send_marks_rejected(env) -> None:
    manager, _channel, repos = env(gateway=FakeGateway(delay=1.0))

    async def scenario() -> None:
        pending = asyncio.create_task(
            manager.request(action="delete_file", reason="pulizia", requester=USER_ID)
        )
        await asyncio.sleep(0.02)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

    asyncio.run(scenario())

    # La riga è stata creata prima dell'invio ed è stata scartata.
    rows = repos.approvals._conn.execute("SELECT status FROM approvals").fetchall()
    assert [row["status"] for row in rows] == ["rejected"]


def test_send_failure_marks_rejected(env) -> None:
    manager, _channel, repos = env(fail=True)

    with pytest.raises(TelegramError):
        asyncio.run(
            manager.request(action="delete_file", reason="pulizia", requester=USER_ID)
        )

    rows = repos.approvals._conn.execute("SELECT status FROM approvals").fetchall()
    assert [row["status"] for row in rows] == ["rejected"]


def test_recover_pending_rejects_everything(env) -> None:
    manager, _channel, repos = env()
    first = repos.approvals.create(
        Approval(action="a", reason="r", expires_at="2026-10-25T09:00:00+00:00")
    )
    second = repos.approvals.create(
        Approval(action="b", reason="r", expires_at="2026-10-25T09:00:00+00:00")
    )

    assert manager.recover_pending() == 2
    assert repos.approvals.get(first.id).status == "rejected"
    assert repos.approvals.get(second.id).status == "rejected"


def test_resolution_is_logged(env, caplog) -> None:
    manager, channel, _repos = env()

    async def scenario():
        pending = asyncio.create_task(
            manager.request(action="delete_file", reason="pulizia", requester=USER_ID)
        )
        await _wait_for_request(channel, manager)
        approval_id = int(channel.sent[0][2][0][0][1].split(":")[1])
        manager.resolve(approval_id, "approved", by_user_id=ADMIN_ID)
        await pending

    with caplog.at_level(logging.INFO, logger="agente.approvals"):
        asyncio.run(scenario())

    record = next(r for r in caplog.records if r.message == "approvazione risolta")
    assert record.decision == "approved"
    assert isinstance(record.duration_ms, int)
