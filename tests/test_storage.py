"""C-02: schema, migrazioni, transazioni, repository."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from agente.errors import StorageError
from agente.storage.db import MIGRATIONS_DIR, Database
from agente.storage.repositories import (
    Approval,
    Execution,
    Message,
    Task,
    User,
    repositories,
)

EXPECTED_TABLES = {
    "tasks",
    "users",
    "subscriptions",
    "executions",
    "conversations",
    "messages",
    "approvals",
    "settings",
    "schema_migrations",
}


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "agente.db")
    database.migrate()
    yield database
    database.close()


def test_migration_creates_spec_tables(db: Database) -> None:
    rows = db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    names = {row["name"] for row in rows}
    assert EXPECTED_TABLES <= names
    assert db.schema_version() == "005_executions_started_index"


def test_spec_columns_are_present(db: Database) -> None:
    expected = {
        "tasks": {"id", "name", "instructions", "schedule_type", "schedule_expr",
                  "state", "log_allowlist", "created_by", "created_at", "updated_at"},
        "users": {"telegram_id", "username", "state", "consent_at", "created_at",
                  "updated_at"},
        "executions": {"id", "task_id", "requested_by", "trigger", "started_at",
                       "finished_at", "outcome", "summary"},
        "approvals": {"id", "action", "reason", "requested_by", "status",
                      "created_at", "expires_at", "resolved_at"},
    }
    for table, columns in expected.items():
        actual = {
            row["name"] for row in db.connection.execute(f"PRAGMA table_info({table})")
        }
        assert columns <= actual, table


def test_database_file_is_private(db: Database) -> None:
    mode = os.stat(db.path).st_mode & 0o777
    assert mode & 0o077 == 0


def test_migrate_is_idempotent(db: Database) -> None:
    assert db.migrate() == []
    assert db.schema_version() == "005_executions_started_index"


def test_repositories_roundtrip(db: Database) -> None:
    repos = repositories(db.connection)
    task = repos.tasks.create(
        Task(
            name="rassegna",
            instructions="cerca notizie",
            schedule_type="orario",
            schedule_expr="08:00",
            log_allowlist=["/tmp/logs"],
            created_by=1,
        )
    )
    assert task.id is not None
    assert repos.tasks.get(task.id).name == "rassegna"

    repos.users.upsert(User(telegram_id=2, username="utente", state="accepted"))
    repos.subscriptions.add(2, task.id)
    assert repos.subscriptions.users_for_task(task.id) == [2]
    assert repos.subscriptions.tasks_for_user(2) == [task.id]

    execution = repos.executions.create(
        Execution(task_id=task.id, trigger="manual", requested_by=2, started_at="2026-10-21T08:00:00+00:00")
    )
    repos.executions.finish(execution.id, finished_at="2026-10-21T08:00:05+00:00", outcome="ok", summary="fatto")
    stored = repos.executions.list(user_id=2)
    assert len(stored) == 1
    assert stored[0].outcome == "ok"

    approval = repos.approvals.create(
        Approval(action="run", reason="test", expires_at="2026-10-21T08:15:00+00:00", requested_by=2)
    )
    assert repos.approvals.get(approval.id).status == "pending"
    repos.approvals.resolve(approval.id, "approved", "2026-10-21T08:10:00+00:00")
    assert repos.approvals.get(approval.id).status == "approved"

    repos.settings.set("last_contact_at", "2026-10-21T08:00:00+00:00")
    assert repos.settings.get("last_contact_at").startswith("2026-10-21")


def test_invalid_state_is_rejected(db: Database) -> None:
    repos = repositories(db.connection)
    task = repos.tasks.create(
        Task(name="t", instructions="i", schedule_type="orario", schedule_expr="09:00", created_by=1)
    )
    with pytest.raises(StorageError):
        repos.tasks.set_state(task.id, "rotto")


def test_transaction_rolls_back(db: Database) -> None:
    db.connection.execute(
        "INSERT INTO settings (key, value) VALUES ('k', 'v')"
    )
    db.connection.commit()
    with pytest.raises(StorageError):
        with db.transaction() as conn:
            conn.execute("INSERT INTO settings (key, value) VALUES ('k2', 'v')")
            conn.execute("INSERT INTO settings (key, value) VALUES ('k', 'duplicato')")
    rows = db.connection.execute(
        "SELECT key FROM settings ORDER BY key"
    ).fetchall()
    assert [row["key"] for row in rows] == ["k"]


def test_messages_retention_helpers(db: Database) -> None:
    repos = repositories(db.connection)
    repos.users.upsert(User(telegram_id=7, state="accepted"))
    repos.conversations.add_message(Message(user_id=7, role="user", content="vecchio", created_at="2026-10-20T08:00:00+00:00"))
    repos.conversations.add_message(Message(user_id=7, role="user", content="nuovo", created_at="2026-10-21T08:00:00+00:00"))
    deleted = repos.conversations.delete_messages_before_for_user(7, "2026-10-21T00:00:00+00:00")
    assert deleted == 1
    remaining = repos.conversations.messages_since(7, "2026-01-01T00:00:00+00:00")
    assert [message.content for message in remaining] == ["nuovo"]


def test_skipped_outcome_is_accepted(db: Database) -> None:
    repos = repositories(db.connection)
    task = repos.tasks.create(
        Task(name="t", instructions="i", schedule_type="orario", schedule_expr="09:00", created_by=1)
    )
    execution = repos.executions.create(
        Execution(task_id=task.id, trigger="scheduled", started_at="2026-10-24T08:00:00+00:00")
    )
    repos.executions.finish(
        execution.id,
        finished_at="2026-10-24T08:00:00+00:00",
        outcome="saltata",
        summary="occorrenza saltata",
    )
    assert repos.executions.list(task_id=task.id)[0].outcome == "saltata"


def test_migration_003_preserves_existing_executions(tmp_path: Path) -> None:
    path = tmp_path / "vecchio.db"
    conn = sqlite3.connect(path)
    conn.executescript((MIGRATIONS_DIR / "001_init.sql").read_text(encoding="utf-8"))
    conn.executescript((MIGRATIONS_DIR / "002_task_name_nocase.sql").read_text(encoding="utf-8"))
    conn.execute(
        "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES ('001_init', '2026-10-21')"
    )
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at)"
        " VALUES ('002_task_name_nocase', '2026-10-21')"
    )
    conn.execute(
        "INSERT INTO tasks (name, instructions, schedule_type, schedule_expr, state,"
        " created_by, created_at, updated_at)"
        " VALUES ('vecchio', 'i', 'orario', '08:00', 'active', 1, '2026-10-20', '2026-10-20')"
    )
    conn.execute(
        "INSERT INTO executions (task_id, trigger, started_at, finished_at, outcome, summary)"
        " VALUES (1, 'scheduled', '2026-10-23T08:00:00+00:00',"
        " '2026-10-23T08:00:05+00:00', 'ok', 'esito precedente')"
    )
    conn.commit()
    conn.close()

    database = Database(path)
    try:
        assert database.migrate() == [
            "003_execution_skipped",
            "004_chat_without_user_fk",
            "005_executions_started_index",
        ]
        rows = database.connection.execute(
            "SELECT task_id, outcome, summary FROM executions"
        ).fetchall()
        assert [(row["task_id"], row["outcome"], row["summary"]) for row in rows] == [
            (1, "ok", "esito precedente")
        ]
        assert database.schema_version() == "005_executions_started_index"
    finally:
        database.close()


def test_chat_tables_have_no_user_fk(db: Database) -> None:
    """Spec 05 D2: l'admin non è in users e deve poter avere una conversazione."""
    for table in ("conversations", "messages"):
        assert db.connection.execute(f"PRAGMA foreign_key_list({table})").fetchall() == []


def test_migration_004_preserves_ids_and_index(tmp_path: Path) -> None:
    path = tmp_path / "chat.db"
    conn = sqlite3.connect(path)
    for name in ("001_init.sql", "002_task_name_nocase.sql", "003_execution_skipped.sql"):
        conn.executescript((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
    conn.execute(
        "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for version in ("001_init", "002_task_name_nocase", "003_execution_skipped"):
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, '2026-10-21')",
            (version,),
        )
    conn.execute(
        "INSERT INTO users (telegram_id, username, state, created_at, updated_at)"
        " VALUES (2, 'utente', 'accepted', '2026-10-21', '2026-10-21')"
    )
    conn.execute(
        "INSERT INTO conversations (user_id, updated_at) VALUES (2, '2026-10-24T10:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO messages (id, user_id, role, content, created_at)"
        " VALUES (5, 2, 'user', 'domanda', '2026-10-24T10:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    database = Database(path)
    try:
        assert database.migrate() == [
            "004_chat_without_user_fk",
            "005_executions_started_index",
        ]
        rows = database.connection.execute(
            "SELECT id, user_id, role, content FROM messages"
        ).fetchall()
        assert [(row["id"], row["user_id"], row["role"], row["content"]) for row in rows] == [
            (5, 2, "user", "domanda")
        ]
        indexes = {
            row["name"]
            for row in database.connection.execute("PRAGMA index_list(messages)")
        }
        assert "idx_messages_user_created" in indexes
    finally:
        database.close()


def test_migration_004_keeps_sqlite_sequence(tmp_path: Path) -> None:
    path = tmp_path / "seq.db"
    conn = sqlite3.connect(path)
    for name in ("001_init.sql", "002_task_name_nocase.sql", "003_execution_skipped.sql"):
        conn.executescript((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
    conn.execute(
        "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for version in ("001_init", "002_task_name_nocase", "003_execution_skipped"):
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, '2026-10-21')",
            (version,),
        )
    conn.execute(
        "INSERT INTO users (telegram_id, username, state, created_at, updated_at)"
        " VALUES (2, 'utente', 'accepted', '2026-10-21', '2026-10-21')"
    )
    conn.execute(
        "INSERT INTO messages (id, user_id, role, content, created_at)"
        " VALUES (7, 2, 'user', 'vecchio', '2026-10-24T10:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    database = Database(path)
    try:
        database.migrate()
        repos = repositories(database.connection)
        new = repos.conversations.add_message(
            Message(user_id=2, role="assistant", content="nuovo")
        )
        # AUTOINCREMENT riparte dopo l'id massimo copiato, senza riusare 7.
        assert new.id == 8
    finally:
        database.close()


def test_reject_pending_updates_only_pending_rows(db: Database) -> None:
    repos = repositories(db.connection)
    pending = repos.approvals.create(
        Approval(action="a", reason="r", expires_at="2026-10-25T09:00:00+00:00")
    )
    approved = repos.approvals.create(
        Approval(action="b", reason="r", expires_at="2026-10-25T09:00:00+00:00")
    )
    repos.approvals.resolve(approved.id, "approved", "2026-10-25T08:10:00+00:00")

    assert repos.approvals.reject_pending("2026-10-25T08:20:00+00:00") == 1
    assert repos.approvals.get(pending.id).status == "rejected"
    assert repos.approvals.get(approved.id).status == "approved"


def test_executions_started_index_exists(db: Database) -> None:
    indexes = {
        row["name"]
        for row in db.connection.execute("PRAGMA index_list(executions)")
    }
    assert "idx_executions_started" in indexes


def test_migration_005_normalizes_offsets_and_naive_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "executions.db"
    conn = sqlite3.connect(path)
    for name in (
        "001_init.sql",
        "002_task_name_nocase.sql",
        "003_execution_skipped.sql",
        "004_chat_without_user_fk.sql",
    ):
        conn.executescript((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
    conn.execute(
        "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for version in (
        "001_init",
        "002_task_name_nocase",
        "003_execution_skipped",
        "004_chat_without_user_fk",
    ):
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, '2026-10-21')",
            (version,),
        )
    conn.execute(
        "INSERT INTO tasks (id, name, instructions, schedule_type, schedule_expr,"
        " state, created_by, created_at, updated_at)"
        " VALUES (1, 't', 'i', 'orario', '08:00', 'active', 1, '2026-10-21',"
        " '2026-10-21')"
    )
    conn.execute(
        "INSERT INTO executions (task_id, trigger, started_at, finished_at, outcome)"
        " VALUES (1, 'scheduled', '2026-11-01T09:00:00+02:00',"
        " '2026-11-01T09:00:05+02:00', 'ok')"
    )
    conn.execute(
        "INSERT INTO executions (task_id, trigger, started_at, outcome)"
        " VALUES (1, 'scheduled', '2026-10-21T08:00:00', 'ok')"
    )
    conn.commit()
    conn.close()

    database = Database(path)
    try:
        assert database.migrate() == ["005_executions_started_index"]
        rows = database.connection.execute(
            "SELECT started_at, finished_at FROM executions ORDER BY id"
        ).fetchall()
        assert rows[0]["started_at"] == "2026-11-01T07:00:00+00:00"
        assert rows[0]["finished_at"] == "2026-11-01T07:00:05+00:00"
        assert rows[1]["started_at"] == "2026-10-21T08:00:00+00:00"
        indexes = {
            row["name"]
            for row in database.connection.execute("PRAGMA index_list(executions)")
        }
        assert "idx_executions_started" in indexes
    finally:
        database.close()


def test_migration_005_tolerates_unparsable_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "broken.db"
    conn = sqlite3.connect(path)
    for name in (
        "001_init.sql",
        "002_task_name_nocase.sql",
        "003_execution_skipped.sql",
        "004_chat_without_user_fk.sql",
    ):
        conn.executescript((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
    conn.execute(
        "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for version in (
        "001_init",
        "002_task_name_nocase",
        "003_execution_skipped",
        "004_chat_without_user_fk",
    ):
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, '2026-10-21')",
            (version,),
        )
    conn.execute(
        "INSERT INTO tasks (id, name, instructions, schedule_type, schedule_expr,"
        " state, created_by, created_at, updated_at)"
        " VALUES (1, 't', 'i', 'orario', '08:00', 'active', 1, '2026-10-21',"
        " '2026-10-21')"
    )
    conn.execute(
        "INSERT INTO executions (task_id, trigger, started_at, outcome)"
        " VALUES (1, 'scheduled', 'non-una-data', 'ok')"
    )
    conn.commit()
    conn.close()

    database = Database(path)
    try:
        assert database.migrate() == ["005_executions_started_index"]
        row = database.connection.execute(
            "SELECT started_at FROM executions"
        ).fetchone()
        assert row["started_at"] == "non-una-data"
    finally:
        database.close()
