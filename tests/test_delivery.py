"""C-20: destinatari autorizzati, consegna e report per destinatario."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agente.delivery import DeliveryService
from agente.errors import DeliveryError, TelegramError
from agente.storage.db import Database
from agente.storage.repositories import Task, User, repositories

ADMIN = 1
USER = 2
REVOKED = 3


class FakeNotifications:
    def __init__(self, fail: tuple[int, ...] = ()) -> None:
        self.fail = set(fail)
        self.sent: list[tuple[int, str]] = []

    async def notify(self, recipients, text: str) -> None:
        for recipient in recipients:
            if recipient in self.fail:
                raise TelegramError("invio fallito")
            self.sent.append((recipient, text))


@pytest.fixture
def env(tmp_path: Path):
    db = Database(tmp_path / "agente.db")
    db.migrate()
    repos = repositories(db.connection)
    repos.users.upsert(User(telegram_id=USER, username="utente", state="accepted"))
    repos.users.upsert(User(telegram_id=REVOKED, username="revocato", state="revoked"))
    task = repos.tasks.create(
        Task(
            name="rassegna",
            instructions="notizie",
            schedule_type="orario",
            schedule_expr="08:00",
            created_by=ADMIN,
        )
    )
    repos.subscriptions.add(USER, task.id)
    repos.subscriptions.add(REVOKED, task.id)
    yield repos, task
    db.close()


def _service(repos, notifications) -> DeliveryService:
    return DeliveryService(
        repos.subscriptions, repos.users, notifications, admin_id=ADMIN
    )


def test_recipients_are_admin_and_accepted_subscribers(env) -> None:
    repos, task = env
    service = _service(repos, FakeNotifications())

    assert service.recipients(task) == (ADMIN, USER)


def test_delivery_sends_result_to_each_recipient(env) -> None:
    repos, task = env
    notifications = FakeNotifications()
    service = _service(repos, notifications)

    report = asyncio.run(service.deliver(task, SimpleNamespace(text="risultato", summary=None)))

    assert report.ok
    assert report.sent == (ADMIN, USER)
    assert notifications.sent == [(ADMIN, "risultato"), (USER, "risultato")]


def test_partial_failure_is_reported(env) -> None:
    repos, task = env
    notifications = FakeNotifications(fail=(USER,))
    service = _service(repos, notifications)

    report = asyncio.run(service.deliver_text(task, "risultato"))

    assert not report.ok
    assert report.sent == (ADMIN,)
    assert report.failed == (USER,)


def test_summary_is_used_when_text_is_empty(env) -> None:
    repos, task = env
    notifications = FakeNotifications()
    service = _service(repos, notifications)

    asyncio.run(service.deliver(task, SimpleNamespace(text="", summary="riassunto")))

    assert notifications.sent[0][1] == "riassunto"


def test_empty_result_is_rejected(env) -> None:
    repos, task = env
    service = _service(repos, FakeNotifications())

    with pytest.raises(ValueError):
        asyncio.run(service.deliver_text(task, "   "))


def test_manual_result_goes_only_to_the_requester(env) -> None:
    repos, task = env
    notifications = FakeNotifications()
    service = _service(repos, notifications)

    report = asyncio.run(service.deliver_text(task, "risultato", requested_by=USER))

    assert report.sent == (USER,)
    assert notifications.sent == [(USER, "risultato")]


def test_manual_result_to_the_admin_is_allowed(env) -> None:
    repos, task = env
    notifications = FakeNotifications()
    service = _service(repos, notifications)

    report = asyncio.run(service.deliver_text(task, "risultato", requested_by=ADMIN))

    assert report.sent == (ADMIN,)


def test_manual_result_to_a_revoked_requester_is_refused(env) -> None:
    repos, task = env
    notifications = FakeNotifications()
    service = _service(repos, notifications)

    with pytest.raises(DeliveryError):
        asyncio.run(service.deliver_text(task, "risultato", requested_by=REVOKED))
    assert notifications.sent == []
