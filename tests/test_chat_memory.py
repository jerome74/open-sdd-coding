"""C-24: contesto, finestra di 24 h, reset e purge (spec 05)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agente.chat_memory import ConversationMemory
from agente.storage.db import Database
from agente.storage.repositories import Message, User, repositories

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
ADMIN = 1
USER = 2
OTHER = 3


def iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


@pytest.fixture
def env(tmp_path: Path):
    db = Database(tmp_path / "chat.db")
    db.migrate()
    repos = repositories(db.connection)
    repos.users.upsert(User(telegram_id=USER, username="utente", state="accepted"))
    repos.users.upsert(User(telegram_id=OTHER, username="altro", state="accepted"))
    memory = ConversationMemory(
        repos.conversations,
        memory_hours=24,
        context_tokens=1000,
        clock=lambda: NOW,
    )

    def build(context_tokens: int = 1000) -> ConversationMemory:
        return ConversationMemory(
            repos.conversations,
            memory_hours=24,
            context_tokens=context_tokens,
            clock=lambda: NOW,
        )

    yield memory, repos, build
    db.close()


def turn(memory: ConversationMemory, user: int, role: str, text: str) -> Message:
    return memory.append(user, Message(user_id=user, role=role, content=text))


def test_append_then_context_returns_both_turns(env) -> None:
    memory, _repos, _build = env
    turn(memory, USER, "user", "che tempo fa?")
    turn(memory, USER, "assistant", "sereno")

    context = memory.get_context(USER)

    assert [(item.role, item.content) for item in context] == [
        ("user", "che tempo fa?"),
        ("assistant", "sereno"),
    ]


def test_context_is_empty_without_a_conversation(env) -> None:
    memory, repos, _build = env
    repos.conversations.add_message(
        Message(user_id=USER, role="user", content="orfano", created_at=iso(NOW))
    )

    assert memory.get_context(USER) == []


def test_context_excludes_messages_older_than_the_window(env) -> None:
    memory, repos, _build = env
    old = iso(NOW - timedelta(hours=25))
    repos.conversations.add_message(
        Message(user_id=USER, role="user", content="vecchio", created_at=old)
    )
    # Conversazione attiva (turno recente) ma con un messaggio fuori finestra.
    repos.conversations.touch(USER, iso(NOW))
    repos.conversations.add_message(
        Message(user_id=USER, role="user", content="recente", created_at=iso(NOW))
    )

    assert [item.content for item in memory.get_context(USER)] == ["recente"]


def test_silence_resets_the_context(env) -> None:
    memory, repos, _build = env
    repos.conversations.add_message(
        Message(
            user_id=USER,
            role="user",
            content="vecchio",
            created_at=iso(NOW - timedelta(hours=25)),
        )
    )
    repos.conversations.touch(USER, iso(NOW - timedelta(hours=25)))

    assert memory.get_context(USER) == []


def test_context_is_truncated_to_the_budget(env) -> None:
    _memory, _repos, build = env
    tight = build(context_tokens=5)  # ~20 caratteri
    turn(tight, USER, "user", "a" * 20)
    turn(tight, USER, "assistant", "b" * 20)
    turn(tight, USER, "user", "c" * 20)

    assert [item.content for item in tight.get_context(USER)] == ["c" * 20]


def test_reset_deletes_every_message_of_the_user(env) -> None:
    memory, _repos, _build = env
    turn(memory, USER, "user", "domanda")
    turn(memory, USER, "assistant", "risposta")
    turn(memory, OTHER, "user", "altra")

    removed = memory.reset(USER)

    assert removed == 3  # due messaggi + la riga di conversazione
    assert memory.get_context(USER) == []
    assert [item.content for item in memory.get_context(OTHER)] == ["altra"]


def test_purge_idle_removes_idle_conversations(env) -> None:
    memory, repos, _build = env
    old = iso(NOW - timedelta(hours=25))
    repos.conversations.add_message(
        Message(user_id=USER, role="user", content="vecchio", created_at=old)
    )
    repos.conversations.touch(USER, old)
    turn(memory, OTHER, "user", "recente")

    stats = memory.purge_idle()

    assert (stats.messages_deleted, stats.conversations_deleted) == (1, 1)
    assert memory.get_context(USER) == []
    assert [item.content for item in memory.get_context(OTHER)] == ["recente"]


def test_admin_can_have_a_conversation(env) -> None:
    memory, _repos, _build = env
    turn(memory, ADMIN, "user", "domanda dell'admin")
    turn(memory, ADMIN, "assistant", "risposta")

    assert [item.content for item in memory.get_context(ADMIN)] == [
        "domanda dell'admin",
        "risposta",
    ]


def test_messages_for_admin_read_respects_the_limit(env) -> None:
    memory, _repos, _build = env
    for index in range(3):
        turn(memory, USER, "user", f"messaggio {index}")

    assert [item.content for item in memory.messages(USER, limit=2)] == [
        "messaggio 1",
        "messaggio 2",
    ]


def test_append_rejects_unknown_roles_and_empty_messages(env) -> None:
    memory, _repos, _build = env

    with pytest.raises(ValueError):
        memory.append(USER, Message(user_id=USER, role="system", content="x"))
    with pytest.raises(ValueError):
        memory.append(USER, Message(user_id=USER, role="user", content="   "))
