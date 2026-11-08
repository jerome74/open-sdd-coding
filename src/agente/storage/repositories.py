"""Repository tipizzati sopra C-02.

Ogni entità della spec 01 ha il suo repository; nessun altro modulo apre SQL.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from ..errors import StorageError
from .db import commit, execute


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Task:
    name: str
    instructions: str
    schedule_type: str
    schedule_expr: str
    state: str = "active"
    log_allowlist: list[str] = field(default_factory=list)
    created_by: int = 0
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class User:
    telegram_id: int
    username: str | None = None
    state: str = "pending"
    consent_at: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Execution:
    task_id: int
    trigger: str
    started_at: str
    requested_by: int | None = None
    finished_at: str | None = None
    outcome: str | None = None
    summary: str | None = None
    id: int | None = None


@dataclass
class Message:
    user_id: int
    role: str
    content: str
    created_at: str = ""
    id: int | None = None


@dataclass
class Approval:
    action: str
    reason: str
    expires_at: str
    requested_by: int | None = None
    status: str = "pending"
    created_at: str = ""
    resolved_at: str | None = None
    id: int | None = None


class TaskRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, task: Task) -> Task:
        now = _now()
        cur = execute(
            self._conn,
            "INSERT INTO tasks (name, instructions, schedule_type, schedule_expr,"
            " state, log_allowlist, created_by, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task.name,
                task.instructions,
                task.schedule_type,
                task.schedule_expr,
                task.state,
                json.dumps(task.log_allowlist),
                task.created_by,
                now,
                now,
            ),
        )
        self._conn.commit()
        task.id = int(cur.lastrowid)
        task.created_at = task.updated_at = now
        return task

    def get(self, task_id: int) -> Task | None:
        row = execute(
            self._conn,"SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return None if row is None else _task(row)

    def get_by_name(self, name: str) -> Task | None:
        """Ricerca per nome senza distinzione di maiuscole (002, piano 02 D3)."""
        row = execute(
            self._conn,
            "SELECT * FROM tasks WHERE name = ? COLLATE NOCASE",
            (name,),
        ).fetchone()
        return None if row is None else _task(row)

    def list(self, state: str | None = None) -> list[Task]:
        if state is None:
            rows = execute(
            self._conn,"SELECT * FROM tasks ORDER BY id").fetchall()
        else:
            rows = execute(
            self._conn,
                "SELECT * FROM tasks WHERE state = ? ORDER BY id", (state,)
            ).fetchall()
        return [_task(row) for row in rows]

    def update(self, task: Task) -> Task:
        if task.id is None:
            raise StorageError("update senza id compito")
        task.updated_at = _now()
        execute(
            self._conn,
            "UPDATE tasks SET name = ?, instructions = ?, schedule_type = ?,"
            " schedule_expr = ?, state = ?, log_allowlist = ?, updated_at = ?"
            " WHERE id = ?",
            (
                task.name,
                task.instructions,
                task.schedule_type,
                task.schedule_expr,
                task.state,
                json.dumps(task.log_allowlist),
                task.updated_at,
                task.id,
            ),
        )
        self._conn.commit()
        return task

    def set_state(self, task_id: int, state: str) -> None:
        if state not in ("active", "paused"):
            raise StorageError(f"stato compito non ammesso: {state}")
        execute(
            self._conn,
            "UPDATE tasks SET state = ?, updated_at = ? WHERE id = ?",
            (state, _now(), task_id),
        )
        self._conn.commit()

    def delete(self, task_id: int) -> None:
        execute(
            self._conn,"DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()


class UserRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, user: User) -> User:
        now = _now()
        existing = self.get(user.telegram_id)
        if existing is None:
            execute(
            self._conn,
                "INSERT INTO users (telegram_id, username, state, consent_at,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user.telegram_id,
                    user.username,
                    user.state,
                    user.consent_at,
                    now,
                    now,
                ),
            )
        else:
            execute(
            self._conn,
                "UPDATE users SET username = ?, state = ?, consent_at = ?,"
                " updated_at = ? WHERE telegram_id = ?",
                (user.username, user.state, user.consent_at, now, user.telegram_id),
            )
        self._conn.commit()
        result = self.get(user.telegram_id)
        assert result is not None
        return result

    def get(self, telegram_id: int) -> User | None:
        row = execute(
            self._conn,
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return None if row is None else _user(row)

    def set_state(self, telegram_id: int, state: str) -> None:
        if state not in ("pending", "accepted", "revoked"):
            raise StorageError(f"stato utente non ammesso: {state}")
        execute(
            self._conn,
            "UPDATE users SET state = ?, updated_at = ? WHERE telegram_id = ?",
            (state, _now(), telegram_id),
        )
        self._conn.commit()

    def set_consent(self, telegram_id: int, consent_at: str | None) -> None:
        execute(
            self._conn,
            "UPDATE users SET consent_at = ?, updated_at = ? WHERE telegram_id = ?",
            (consent_at, _now(), telegram_id),
        )
        self._conn.commit()

    def list(self, state: str | None = None) -> list[User]:
        if state is None:
            rows = execute(
            self._conn,"SELECT * FROM users ORDER BY telegram_id").fetchall()
        else:
            rows = execute(
            self._conn,
                "SELECT * FROM users WHERE state = ? ORDER BY telegram_id", (state,)
            ).fetchall()
        return [_user(row) for row in rows]


class SubscriptionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, user_id: int, task_id: int) -> None:
        execute(
            self._conn,
            "INSERT OR IGNORE INTO subscriptions (user_id, task_id) VALUES (?, ?)",
            (user_id, task_id),
        )
        self._conn.commit()

    def remove(self, user_id: int, task_id: int) -> None:
        execute(
            self._conn,
            "DELETE FROM subscriptions WHERE user_id = ? AND task_id = ?",
            (user_id, task_id),
        )
        self._conn.commit()

    def users_for_task(self, task_id: int) -> list[int]:
        rows = execute(
            self._conn,
            "SELECT user_id FROM subscriptions WHERE task_id = ? ORDER BY user_id",
            (task_id,),
        ).fetchall()
        return [int(row["user_id"]) for row in rows]

    def tasks_for_user(self, user_id: int) -> list[int]:
        rows = execute(
            self._conn,
            "SELECT task_id FROM subscriptions WHERE user_id = ? ORDER BY task_id",
            (user_id,),
        ).fetchall()
        return [int(row["task_id"]) for row in rows]


class ExecutionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, execution: Execution) -> Execution:
        cur = execute(
            self._conn,
            "INSERT INTO executions (task_id, requested_by, trigger, started_at,"
            " finished_at, outcome, summary) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                execution.task_id,
                execution.requested_by,
                execution.trigger,
                execution.started_at,
                execution.finished_at,
                execution.outcome,
                execution.summary,
            ),
        )
        self._conn.commit()
        execution.id = int(cur.lastrowid)
        return execution

    def finish(
        self,
        execution_id: int,
        *,
        finished_at: str,
        outcome: str,
        summary: str | None,
    ) -> None:
        if outcome not in ("ok", "errore", "interrotto", "saltata"):
            raise StorageError(f"esito non ammesso: {outcome}")
        execute(
            self._conn,
            "UPDATE executions SET finished_at = ?, outcome = ?, summary = ? WHERE id = ?",
            (finished_at, outcome, summary, execution_id),
        )
        self._conn.commit()

    def list(
        self,
        *,
        user_id: int | None = None,
        since: str | None = None,
        until: str | None = None,
        task_id: int | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[Execution]:
        clauses: list[str] = []
        params: list[object] = []
        if user_id is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM subscriptions s"
                " WHERE s.task_id = executions.task_id AND s.user_id = ?)"
            )
            params.append(user_id)
        if since is not None:
            clauses.append("executions.started_at >= ?")
            params.append(since)
        if until is not None:
            clauses.append("executions.started_at <= ?")
            params.append(until)
        if task_id is not None:
            clauses.append("executions.task_id = ?")
            params.append(task_id)
        if outcome is not None:
            clauses.append("executions.outcome = ?")
            params.append(outcome)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = execute(
            self._conn,
            "SELECT * FROM executions" + where + " ORDER BY started_at DESC, id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [_execution(row) for row in rows]

    def delete_before(self, cutoff: str) -> int:
        cur = execute(
            self._conn,
            "DELETE FROM executions WHERE started_at < ?", (cutoff,)
        )
        commit(self._conn)
        return cur.rowcount


class ConversationRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def touch(self, user_id: int, updated_at: str | None = None) -> None:
        moment = updated_at or _now()
        execute(
            self._conn,
            "INSERT INTO conversations (user_id, updated_at) VALUES (?, ?)"
            " ON CONFLICT(user_id) DO UPDATE SET updated_at = excluded.updated_at",
            (user_id, moment),
        )
        self._conn.commit()

    def updated_at(self, user_id: int) -> str | None:
        row = execute(
            self._conn,
            "SELECT updated_at FROM conversations WHERE user_id = ?", (user_id,)
        ).fetchone()
        return None if row is None else str(row["updated_at"])

    def add_message(self, message: Message) -> Message:
        message.created_at = message.created_at or _now()
        cur = execute(
            self._conn,
            "INSERT INTO messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (message.user_id, message.role, message.content, message.created_at),
        )
        self._conn.commit()
        message.id = int(cur.lastrowid)
        return message

    def messages_since(self, user_id: int, since: str) -> list[Message]:
        rows = execute(
            self._conn,
            "SELECT * FROM messages WHERE user_id = ? AND created_at >= ?"
            " ORDER BY created_at, id",
            (user_id, since),
        ).fetchall()
        return [_message(row) for row in rows]

    def messages_for_user(
        self,
        user_id: int,
        *,
        since: str | None = None,
        limit: int | None = None,
    ) -> list[Message]:
        """Messaggi dell'utente in ordine cronologico (ultimi ``limit`` se dato)."""
        where = "user_id = ?"
        params: list[object] = [user_id]
        if since is not None:
            where += " AND created_at >= ?"
            params.append(since)
        if limit is None:
            rows = execute(
                self._conn,
                f"SELECT * FROM messages WHERE {where} ORDER BY created_at, id",
                tuple(params),
            ).fetchall()
            return [_message(row) for row in rows]
        # Le ultime `limit` righe, restituite in ordine cronologico.
        rows = execute(
            self._conn,
            "SELECT * FROM ("
            f" SELECT * FROM messages WHERE {where}"
            " ORDER BY created_at DESC, id DESC LIMIT ?"
            ") ORDER BY created_at, id",
            tuple(params) + (limit,),
        ).fetchall()
        return [_message(row) for row in rows]

    def delete_all_for_user(self, user_id: int) -> tuple[int, int]:
        """Cancella messaggi e conversazione dell'utente: ``(messaggi, conversazioni)``."""
        messages = execute(
            self._conn, "DELETE FROM messages WHERE user_id = ?", (user_id,)
        ).rowcount
        conversations = execute(
            self._conn, "DELETE FROM conversations WHERE user_id = ?", (user_id,)
        ).rowcount
        self._conn.commit()
        return messages, conversations

    def delete_idle(self, cutoff: str) -> tuple[int, int]:
        """Cancella le conversazioni silenti e i loro messaggi: ``(messaggi, conversazioni)``."""
        messages = execute(
            self._conn,
            "DELETE FROM messages WHERE user_id IN ("
            " SELECT user_id FROM conversations WHERE updated_at < ?"
            ")",
            (cutoff,),
        ).rowcount
        conversations = execute(
            self._conn,
            "DELETE FROM conversations WHERE updated_at < ?",
            (cutoff,),
        ).rowcount
        self._conn.commit()
        return messages, conversations

    def delete_messages_before(self, cutoff: str) -> int:
        cur = execute(
            self._conn,"DELETE FROM messages WHERE created_at < ?", (cutoff,))
        commit(self._conn)
        return cur.rowcount

    def delete_messages_before_for_user(self, user_id: int, cutoff: str) -> int:
        cur = execute(
            self._conn,
            "DELETE FROM messages WHERE user_id = ? AND created_at < ?",
            (user_id, cutoff),
        )
        commit(self._conn)
        return cur.rowcount


class ApprovalRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, approval: Approval) -> Approval:
        approval.created_at = _now()
        cur = execute(
            self._conn,
            "INSERT INTO approvals (action, reason, requested_by, status, created_at,"
            " expires_at, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                approval.action,
                approval.reason,
                approval.requested_by,
                approval.status,
                approval.created_at,
                approval.expires_at,
                approval.resolved_at,
            ),
        )
        self._conn.commit()
        approval.id = int(cur.lastrowid)
        return approval

    def get(self, approval_id: int) -> Approval | None:
        row = execute(
            self._conn,
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        return None if row is None else _approval(row)

    def resolve(self, approval_id: int, status: str, resolved_at: str) -> None:
        if status not in ("approved", "rejected"):
            raise StorageError(f"esito approvazione non ammesso: {status}")
        execute(
            self._conn,
            "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ? AND status = 'pending'",
            (status, resolved_at, approval_id),
        )
        self._conn.commit()

    def expire_pending(self, now: str) -> int:
        cur = execute(
            self._conn,
            "UPDATE approvals SET status = 'rejected', resolved_at = ?"
            " WHERE status = 'pending' AND expires_at <= ?",
            (now, now),
        )
        self._conn.commit()
        return cur.rowcount

    def reject_pending(self, resolved_at: str) -> int:
        """Scarta tutte le richieste ancora aperte (riavvio, spec 06 D4)."""
        cur = execute(
            self._conn,
            "UPDATE approvals SET status = 'rejected', resolved_at = ?"
            " WHERE status = 'pending'",
            (resolved_at,),
        )
        self._conn.commit()
        return cur.rowcount


class SettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: str, default: str | None = None) -> str | None:
        row = execute(
            self._conn,
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return default if row is None else str(row["value"])

    def set(self, key: str, value: str) -> None:
        execute(
            self._conn,
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def delete(self, key: str) -> None:
        execute(
            self._conn,"DELETE FROM settings WHERE key = ?", (key,))
        self._conn.commit()


@dataclass(frozen=True)
class Repositories:
    tasks: TaskRepository
    users: UserRepository
    subscriptions: SubscriptionRepository
    executions: ExecutionRepository
    conversations: ConversationRepository
    approvals: ApprovalRepository
    settings: SettingsRepository


def repositories(conn: sqlite3.Connection) -> Repositories:
    return Repositories(
        tasks=TaskRepository(conn),
        users=UserRepository(conn),
        subscriptions=SubscriptionRepository(conn),
        executions=ExecutionRepository(conn),
        conversations=ConversationRepository(conn),
        approvals=ApprovalRepository(conn),
        settings=SettingsRepository(conn),
    )


def _task(row: sqlite3.Row) -> Task:
    return Task(
        id=int(row["id"]),
        name=str(row["name"]),
        instructions=str(row["instructions"]),
        schedule_type=str(row["schedule_type"]),
        schedule_expr=str(row["schedule_expr"]),
        state=str(row["state"]),
        log_allowlist=list(json.loads(row["log_allowlist"])),
        created_by=int(row["created_by"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _user(row: sqlite3.Row) -> User:
    return User(
        telegram_id=int(row["telegram_id"]),
        username=row["username"],
        state=str(row["state"]),
        consent_at=row["consent_at"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _execution(row: sqlite3.Row) -> Execution:
    return Execution(
        id=int(row["id"]),
        task_id=int(row["task_id"]),
        requested_by=row["requested_by"],
        trigger=str(row["trigger"]),
        started_at=str(row["started_at"]),
        finished_at=row["finished_at"],
        outcome=row["outcome"],
        summary=row["summary"],
    )


def _message(row: sqlite3.Row) -> Message:
    return Message(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        role=str(row["role"]),
        content=str(row["content"]),
        created_at=str(row["created_at"]),
    )


def _approval(row: sqlite3.Row) -> Approval:
    return Approval(
        id=int(row["id"]),
        action=str(row["action"]),
        reason=str(row["reason"]),
        requested_by=row["requested_by"],
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        expires_at=str(row["expires_at"]),
        resolved_at=row["resolved_at"],
    )
