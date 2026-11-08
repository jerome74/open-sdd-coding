"""C-11: storico per ruolo, retention 30 giorni, reset chat 24 ore."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agente.history import HistoryService
from agente.storage.db import Database
from agente.storage.repositories import Message, Task, User, repositories

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def env(tmp_path: Path):
    db = Database(tmp_path / "h.db")
    db.migrate()
    repos = repositories(db.connection)
    task = repos.tasks.create(
        Task(name="t", instructions="i", schedule_type="orario", schedule_expr="08:00", created_by=1)
    )
    repos.users.upsert(User(telegram_id=2, state="accepted"))
    repos.users.upsert(User(telegram_id=3, state="accepted"))
    repos.subscriptions.add(2, task.id)
    service = HistoryService(
        repos.executions,
        repos.conversations,
        retention_days=30,
        chat_memory_hours=24,
        clock=lambda: NOW,
    )
    yield service, repos, task
    db.close()


def test_record_and_query_by_user_and_outcome(env) -> None:
    service, repos, task = env
    first = service.record(task_id=task.id, trigger="scheduled", requested_by=2, started_at="2026-10-21T08:00:00+00:00")
    service.finish(first.id, outcome="ok", summary="fatto")
    second = service.record(task_id=task.id, trigger="manual", requested_by=2, started_at="2026-10-21T09:00:00+00:00")
    service.finish(second.id, outcome="errore", summary="boom")

    assert [item.outcome for item in service.query(user_id=2)] == ["errore", "ok"]
    assert [item.outcome for item in service.query(user_id=3)] == []
    assert [item.id for item in service.query(outcome="ok")] == [first.id]


def test_purge_removes_old_executions_and_messages(env) -> None:
    service, repos, task = env
    old = service.record(task_id=task.id, trigger="scheduled", requested_by=2, started_at="2026-09-01T08:00:00+00:00")
    service.finish(old.id, outcome="ok", summary="vecchio")
    recent = service.record(task_id=task.id, trigger="scheduled", requested_by=2, started_at="2026-10-20T08:00:00+00:00")
    service.finish(recent.id, outcome="ok", summary="recente")

    repos.conversations.add_message(Message(user_id=2, role="user", content="vecchio", created_at="2026-10-19T08:00:00+00:00"))
    repos.conversations.add_message(Message(user_id=2, role="user", content="recente", created_at="2026-10-21T08:00:00+00:00"))

    stats = service.purge_expired()
    assert stats.executions_deleted == 1
    assert stats.messages_deleted == 1
    assert [item.id for item in service.query()] == [recent.id]


def test_reset_conversation_only_for_that_user(env) -> None:
    service, repos, task = env
    repos.conversations.add_message(Message(user_id=2, role="user", content="vecchio", created_at="2026-10-19T08:00:00+00:00"))
    repos.conversations.add_message(Message(user_id=3, role="user", content="vecchio", created_at="2026-10-19T08:00:00+00:00"))

    service.reset_conversation(2)
    assert repos.conversations.messages_since(2, "2026-01-01T00:00:00+00:00") == []
    assert len(repos.conversations.messages_since(3, "2026-01-01T00:00:00+00:00")) == 1


def test_record_normalizes_offsets(env) -> None:
    service, repos, task = env

    execution = service.record(
        task_id=task.id,
        trigger="scheduled",
        requested_by=2,
        started_at="2026-10-21T09:00:00+02:00",
    )

    assert repos.executions.list()[0].started_at == "2026-10-21T07:00:00+00:00"
    assert execution.started_at == "2026-10-21T07:00:00+00:00"


def test_record_skipped_is_normalized(env) -> None:
    service, repos, task = env

    service.record_skipped(
        task_id=task.id, occurred_at="2026-10-21T09:00:00+02:00"
    )

    row = repos.executions.list()[0]
    assert row.started_at == "2026-10-21T07:00:00+00:00"
    assert row.finished_at == "2026-10-21T07:00:00+00:00"
    assert row.summary == "occorrenza saltata: 2026-10-21T07:00:00+00:00"


def test_skipped_note_is_preserved(env) -> None:
    service, repos, task = env

    service.record_skipped(
        task_id=task.id,
        occurred_at="2026-10-21T09:00:00+02:00",
        note="occorrenza saltata: 2026-10-21T09:00:00+02:00",
    )

    assert repos.executions.list()[0].summary == "occorrenza saltata: 2026-10-21T09:00:00+02:00"


def test_query_orders_across_offsets(env) -> None:
    service, repos, task = env
    service.record(
        task_id=task.id, trigger="scheduled", requested_by=2,
        started_at="2026-10-21T10:00:00+02:00",
    )
    service.record(
        task_id=task.id, trigger="scheduled", requested_by=2,
        started_at="2026-10-21T08:30:00+00:00",
    )

    rows = service.query(user_id=2)

    assert [row.started_at for row in rows] == [
        "2026-10-21T08:30:00+00:00",
        "2026-10-21T08:00:00+00:00",
    ]


def test_purge_uses_utc_cutoff(tmp_path: Path) -> None:
    db = Database(tmp_path / "cutoff.db")
    db.migrate()
    repos = repositories(db.connection)
    task = repos.tasks.create(
        Task(name="t", instructions="i", schedule_type="orario", schedule_expr="08:00", created_by=1)
    )
    local_clock = lambda: datetime(2026, 10, 21, 14, 0, tzinfo=timezone(timedelta(hours=2)))
    service = HistoryService(
        repos.executions,
        repos.conversations,
        retention_days=30,
        chat_memory_hours=24,
        clock=local_clock,
    )
    old = service.record(
        task_id=task.id, trigger="scheduled", requested_by=None,
        started_at="2026-09-21T11:00:00+00:00",
    )
    recent = service.record(
        task_id=task.id, trigger="scheduled", requested_by=None,
        started_at="2026-09-21T13:00:00+00:00",
    )

    stats = service.purge_expired()

    assert stats.executions_deleted == 1
    assert [row.id for row in service.query()] == [recent.id]
    db.close()


def test_reset_uses_utc_cutoff(tmp_path: Path) -> None:
    db = Database(tmp_path / "reset.db")
    db.migrate()
    repos = repositories(db.connection)
    repos.users.upsert(User(telegram_id=2, state="accepted"))
    local_clock = lambda: datetime(2026, 10, 21, 14, 0, tzinfo=timezone(timedelta(hours=2)))
    service = HistoryService(
        repos.executions,
        repos.conversations,
        retention_days=30,
        chat_memory_hours=24,
        clock=local_clock,
    )
    repos.conversations.add_message(
        Message(user_id=2, role="user", content="vecchio", created_at="2026-10-19T11:00:00+00:00")
    )
    repos.conversations.add_message(
        Message(user_id=2, role="user", content="recente", created_at="2026-10-21T11:00:00+00:00")
    )

    service.reset_conversation(2)

    messages = repos.conversations.messages_since(2, "2026-01-01T00:00:00+00:00")
    assert [message.content for message in messages] == ["recente"]
    db.close()


def test_purge_logs_the_deleted_counts(env, caplog) -> None:
    service, repos, task = env
    old = service.record(
        task_id=task.id, trigger="scheduled", requested_by=2,
        started_at="2026-09-01T08:00:00+00:00",
    )
    service.finish(old.id, outcome="ok", summary="vecchio")

    with caplog.at_level(logging.INFO, logger="agente.history"):
        stats = service.purge_expired()

    assert stats.executions_deleted == 1
    assert any(record.message == "retention esecuzioni" for record in caplog.records)
    assert any(record.message == "retention messaggi" for record in caplog.records)
