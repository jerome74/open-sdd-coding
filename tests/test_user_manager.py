"""C-31: utenti, transizioni di stato e iscrizioni (spec 08)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from agente.consent import ConsentFlow
from agente.consent import PRIVACY_NOTICE
from agente.errors import TelegramError, UserAccessError
from agente.notifications import NotificationService
from agente.role_guard import RoleGuard
from agente.storage.db import Database
from agente.storage.repositories import Task, User, repositories
from agente.user_manager import UserManager
from agente.user_state import MAX_AUTHORIZED_USERS

ADMIN = 1
USER = 2
NOW = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)


class Gateway:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []
        self.fail_chats: set[int] = set()

    async def send(self, chat_id, text, keyboard=None) -> None:
        if chat_id in self.fail_chats:
            raise TelegramError("rete")
        self.sent.append((chat_id, text, keyboard))

    def texts(self) -> list[str]:
        return [text for _, text, _ in self.sent]


@pytest.fixture
def env(tmp_path, make_config):
    db = Database(tmp_path / "users.db")
    db.migrate()
    repos = repositories(db.connection)
    gateway = Gateway()
    config = make_config(admin_id=ADMIN)
    roles = RoleGuard(config, repos.users)
    notifications = NotificationService(gateway, config, repos.approvals)
    consent = ConsentFlow(repos.users, notifications, clock=lambda: NOW)
    manager = UserManager(
        repos.users, repos.subscriptions, repos.tasks, consent, roles
    )
    yield manager, repos, gateway
    db.close()


def _task(repos, name: str = "news") -> Task:
    return repos.tasks.create(
        Task(
            name=name,
            instructions="riassumi",
            schedule_type="orario",
            schedule_expr="08:00",
            created_by=ADMIN,
        )
    )


def _accepted(repos, telegram_id: int) -> User:
    return repos.users.upsert(
        User(telegram_id=telegram_id, username=f"u{telegram_id}", state="accepted")
    )


def test_authorize_creates_pending_and_sends_the_notice(env) -> None:
    manager, repos, gateway = env

    result = asyncio.run(manager.authorize(ADMIN, USER, username="mario"))

    assert result.changed is True
    assert result.notice_sent is True
    assert result.user.state == "pending"
    assert result.user.username == "mario"
    assert gateway.sent[0][:2] == (USER, PRIVACY_NOTICE)
    assert "in attesa" in result.note


def test_non_admin_cannot_manage_users(env) -> None:
    manager, repos, _gateway = env
    _accepted(repos, USER)

    with pytest.raises(UserAccessError) as caught:
        asyncio.run(manager.authorize(USER, 99))
    assert caught.value.reason == "forbidden"

    with pytest.raises(UserAccessError) as caught:
        manager.revoke(USER, USER)
    assert caught.value.reason == "forbidden"

    with pytest.raises(UserAccessError) as caught:
        manager.list_users(USER)
    assert caught.value.reason == "forbidden"

    assert repos.users.get(99) is None


def test_administrator_is_not_a_user_target(env) -> None:
    manager, repos, _gateway = env

    with pytest.raises(UserAccessError) as caught:
        asyncio.run(manager.authorize(ADMIN, ADMIN))
    assert caught.value.reason == "invalid_target"

    with pytest.raises(UserAccessError) as caught:
        manager.revoke(ADMIN, ADMIN)
    assert caught.value.reason == "invalid_target"

    assert repos.users.get(ADMIN) is None


def test_already_authorized_user_is_not_reinvited(env) -> None:
    manager, repos, gateway = env
    _accepted(repos, USER)

    result = asyncio.run(manager.authorize(ADMIN, USER))

    assert result.changed is False
    assert result.notice_sent is False
    assert result.user.state == "accepted"
    assert "già autorizzato" in result.note
    assert gateway.sent == []


def test_reauthorizing_a_revoked_user_clears_consent(env) -> None:
    manager, repos, _gateway = env
    repos.users.upsert(
        User(
            telegram_id=USER,
            username="mario",
            state="revoked",
            consent_at="2026-10-01T08:00:00+00:00",
        )
    )

    result = asyncio.run(manager.authorize(ADMIN, USER))

    assert result.changed is True
    assert result.user.state == "pending"
    assert result.user.consent_at is None
    assert result.user.username == "mario"


def test_authorize_preserves_the_username(env) -> None:
    manager, repos, _gateway = env
    repos.users.upsert(User(telegram_id=USER, username="mario", state="pending"))

    result = asyncio.run(manager.authorize(ADMIN, USER))

    assert result.user.username == "mario"


def test_resend_to_pending_is_not_a_change(env) -> None:
    manager, repos, _gateway = env
    repos.users.upsert(User(telegram_id=USER, username="mario", state="pending"))

    result = asyncio.run(manager.authorize(ADMIN, USER))

    assert result.changed is False
    assert result.notice_sent is True
    assert "in attesa" in result.note


def test_failed_notice_is_reported(env) -> None:
    manager, repos, gateway = env
    gateway.fail_chats = {USER}

    result = asyncio.run(manager.authorize(ADMIN, USER))

    assert result.notice_sent is False
    assert "non inviata" in result.note
    assert repos.users.get(USER).state == "pending"
    assert gateway.sent[-1][0] == ADMIN


def test_sixth_user_is_refused(env) -> None:
    manager, repos, _gateway = env
    for index in range(MAX_AUTHORIZED_USERS):
        _accepted(repos, 100 + index)

    with pytest.raises(UserAccessError) as caught:
        asyncio.run(manager.authorize(ADMIN, USER))

    assert caught.value.reason == "limit"
    assert repos.users.get(USER) is None


def test_already_authorized_user_does_not_hit_the_limit(env) -> None:
    manager, repos, _gateway = env
    for index in range(MAX_AUTHORIZED_USERS):
        _accepted(repos, 100 + index)

    result = asyncio.run(manager.authorize(ADMIN, 100))

    assert result.changed is False
    assert "già autorizzato" in result.note


def test_reopening_a_revoked_user_is_refused_at_the_limit(env) -> None:
    manager, repos, _gateway = env
    for index in range(MAX_AUTHORIZED_USERS):
        _accepted(repos, 100 + index)
    repos.users.upsert(User(telegram_id=USER, state="revoked"))

    with pytest.raises(UserAccessError) as caught:
        asyncio.run(manager.authorize(ADMIN, USER))

    assert caught.value.reason == "limit"
    assert repos.users.get(USER).state == "revoked"


def test_pending_resend_is_allowed_at_the_limit(env) -> None:
    manager, repos, _gateway = env
    for index in range(MAX_AUTHORIZED_USERS):
        _accepted(repos, 100 + index)
    repos.users.upsert(User(telegram_id=USER, state="pending"))

    result = asyncio.run(manager.authorize(ADMIN, USER))

    assert result.notice_sent is True
    assert repos.users.get(USER).state == "pending"


def test_revoke_keeps_the_subscriptions(env) -> None:
    manager, repos, _gateway = env
    _accepted(repos, USER)
    task = _task(repos)
    manager.subscribe(ADMIN, USER, task.id)

    result = manager.revoke(ADMIN, USER)

    assert result.changed is True
    assert result.user.state == "revoked"
    assert repos.subscriptions.tasks_for_user(USER) == [task.id]


def test_revoking_twice_is_not_a_change(env) -> None:
    manager, repos, _gateway = env
    repos.users.upsert(User(telegram_id=USER, state="revoked"))

    result = manager.revoke(ADMIN, USER)

    assert result.changed is False
    assert "era già revocato" in result.note


def test_revoke_unknown_user_is_not_found(env) -> None:
    manager, _repos, _gateway = env

    with pytest.raises(UserAccessError) as caught:
        manager.revoke(ADMIN, 404)

    assert caught.value.reason == "not_found"


def test_subscribe_requires_an_accepted_user(env) -> None:
    manager, repos, _gateway = env
    repos.users.upsert(User(telegram_id=USER, state="pending"))
    task = _task(repos)

    with pytest.raises(UserAccessError) as caught:
        manager.subscribe(ADMIN, USER, task.id)

    assert caught.value.reason == "invalid_state"


def test_subscribe_and_unsubscribe(env) -> None:
    manager, repos, _gateway = env
    _accepted(repos, USER)
    task = _task(repos)

    added = manager.subscribe(ADMIN, USER, task.id)
    again = manager.subscribe(ADMIN, USER, task.id)
    removed = manager.unsubscribe(ADMIN, USER, task.id)
    twice = manager.unsubscribe(ADMIN, USER, task.id)

    assert added.changed is True and "iscritto" in added.note
    assert again.changed is False and "già iscritto" in again.note
    assert removed.changed is True and "disiscritto" in removed.note
    assert twice.changed is False and "non è iscritto" in twice.note
    assert repos.subscriptions.tasks_for_user(USER) == []


def test_subscribe_unknown_task_is_not_found(env) -> None:
    manager, repos, _gateway = env
    _accepted(repos, USER)

    with pytest.raises(UserAccessError) as caught:
        manager.subscribe(ADMIN, USER, 999)

    assert caught.value.reason == "not_found"


def test_unsubscribe_is_allowed_for_a_revoked_user(env) -> None:
    manager, repos, _gateway = env
    _accepted(repos, USER)
    task = _task(repos)
    manager.subscribe(ADMIN, USER, task.id)
    manager.revoke(ADMIN, USER)

    result = manager.unsubscribe(ADMIN, USER, task.id)

    assert result.changed is True


def test_list_users_reports_state_and_tasks(env) -> None:
    manager, repos, _gateway = env
    _accepted(repos, USER)
    task = _task(repos)
    manager.subscribe(ADMIN, USER, task.id)
    repos.users.upsert(User(telegram_id=3, username="anna", state="pending"))

    views = manager.list_users(ADMIN)

    assert [view.user.telegram_id for view in views] == [USER, 3]
    assert views[0].task_names == ("news",)
    assert views[1].task_names == ()
    assert views[1].user.state == "pending"


def test_subscribing_twice_is_not_a_change(env) -> None:
    manager, repos, _gateway = env
    _accepted(repos, USER)
    task = _task(repos)
    manager.subscribe(ADMIN, USER, task.id)

    result = manager.subscribe(ADMIN, USER, task.id)

    assert result.changed is False
    assert "già iscritto" in result.note


def test_failed_resend_reports_the_failure_clearly(env) -> None:
    manager, repos, gateway = env
    repos.users.upsert(User(telegram_id=USER, username="mario", state="pending"))
    gateway.fail_chats = {USER}

    result = asyncio.run(manager.authorize(ADMIN, USER))

    assert result.notice_sent is False
    assert result.note == f"Utente {USER} in attesa, informativa non inviata."
    assert "rnon" not in result.note
