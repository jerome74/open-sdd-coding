"""C-10: split messaggi, avvisi admin, richieste di conferma."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from agente.notifications import MAX_MESSAGE_LENGTH, NotificationService, split_message
from agente.storage.db import Database
from agente.storage.repositories import Approval, repositories


class FakeGateway:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []

    async def send(self, chat_id, text, keyboard=None) -> None:
        self.sent.append((chat_id, text, keyboard))


def test_split_short_message_is_unchanged() -> None:
    assert split_message("ciao") == ["ciao"]


def test_split_prefers_newlines_and_loses_nothing() -> None:
    text = "\n".join(["x" * 100 for _ in range(60)])
    chunks = split_message(text, limit=500)
    assert all(len(chunk) <= 500 for chunk in chunks)
    assert "".join(chunk.replace("\n", "") for chunk in chunks) == text.replace("\n", "")


def test_split_unbroken_text() -> None:
    chunks = split_message("a" * (MAX_MESSAGE_LENGTH * 2 + 10))
    assert [len(chunk) for chunk in chunks] == [MAX_MESSAGE_LENGTH, MAX_MESSAGE_LENGTH, 10]


def test_notify_and_alert_admin(tmp_path) -> None:
    db = Database(tmp_path / "n.db")
    db.migrate()
    gateway = FakeGateway()
    config = _config(tmp_path)
    service = NotificationService(gateway, config, repositories(db.connection).approvals)

    asyncio.run(service.notify([2, 3], "risultato"))
    assert [chat_id for chat_id, _, _ in gateway.sent] == [2, 3]

    asyncio.run(service.alert_admin("guasto"))
    assert gateway.sent[-1][0] == config.admin_telegram_id
    assert "guasto" in gateway.sent[-1][1]
    db.close()


def test_request_approval_persists_and_expires_in_15_minutes(tmp_path) -> None:
    db = Database(tmp_path / "n.db")
    db.migrate()
    gateway = FakeGateway()
    now = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)
    config = _config(tmp_path)
    repos = repositories(db.connection)
    service = NotificationService(
        gateway, config, repos.approvals, clock=lambda: now
    )

    approval = asyncio.run(
        service.request_approval(action="run_command", reason="rm file", requested_by=2)
    )
    assert approval.id is not None
    assert approval.expires_at == "2026-10-21T08:15:00+00:00"
    assert repos.approvals.get(approval.id).status == "pending"

    chat_id, text, keyboard = gateway.sent[-1]
    assert chat_id == config.admin_telegram_id
    assert "run_command" in text
    assert keyboard[0][0][0] == "Approva"
    assert keyboard[0][1][0] == "Rifiuta"

    expired = repos.approvals.expire_pending("2026-10-21T08:16:00+00:00")
    assert expired == 1
    assert repos.approvals.get(approval.id).status == "rejected"
    db.close()


def _config(tmp_path):
    from agente.config import (
        Config,
        DeepSeekConfig,
        LimitsConfig,
        PathsConfig,
        SearchConfig,
        TelegramConfig,
    )

    return Config(
        admin_telegram_id=1,
        telegram=TelegramConfig(token="t"),
        deepseek=DeepSeekConfig(
            model="deepseek-flash",
            api_base="https://api.deepseek.test/v1",
            api_key="k",
            max_context_tokens=100,
        ),
        search=SearchConfig(),
        paths=PathsConfig(db=tmp_path / "n.db", logs=tmp_path / "logs"),
        limits=LimitsConfig(),
    )


def test_send_approval_uses_the_existing_format(tmp_path) -> None:
    db = Database(tmp_path / "n.db")
    db.migrate()
    gateway = FakeGateway()
    config = _config(tmp_path)
    repos = repositories(db.connection)
    service = NotificationService(gateway, config, repos.approvals)
    approval = repos.approvals.create(
        Approval(
            action="delete_file /tmp/x",
            reason="pulizia",
            expires_at="2026-10-25T10:00:00+00:00",
            requested_by=2,
        )
    )

    asyncio.run(service.send_approval(approval))

    chat_id, text, keyboard = gateway.sent[-1]
    assert chat_id == config.admin_telegram_id
    assert "delete_file /tmp/x" in text and "pulizia" in text
    assert keyboard[0][0][1] == f"approval:{approval.id}:approve"
    assert keyboard[0][1][1] == f"approval:{approval.id}:reject"
    db.close()


def test_alert_admin_forwards_the_keyboard(tmp_path) -> None:
    db = Database(tmp_path / "n.db")
    db.migrate()
    gateway = FakeGateway()
    config = _config(tmp_path)
    service = NotificationService(gateway, config, repositories(db.connection).approvals)

    asyncio.run(
        service.alert_admin("nuovo", keyboard=((("Autorizza", "authorize:42"),),))
    )

    assert gateway.sent[-1][0] == config.admin_telegram_id
    assert gateway.sent[-1][2] == ((("Autorizza", "authorize:42"),),)
    db.close()


def test_keyboard_goes_on_the_last_chunk(tmp_path) -> None:
    db = Database(tmp_path / "n.db")
    db.migrate()
    gateway = FakeGateway()
    config = _config(tmp_path)
    service = NotificationService(gateway, config, repositories(db.connection).approvals)
    keyboard = ((("Accetto", "consent:accept"),),)

    asyncio.run(service.notify([2], "a" * 5000, keyboard=keyboard))

    assert len(gateway.sent) == 2
    assert [keyboard_value for _, _, keyboard_value in gateway.sent] == [None, keyboard]
    db.close()
