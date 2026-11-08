"""C-02 Storage — unico accesso a SQLite, migrazioni e transazioni."""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..errors import StorageError

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_SCHEMA_TABLE = "schema_migrations"
_LOCK_RETRY_ATTEMPTS = 3
_LOCK_RETRY_DELAY_S = 0.1

logger = logging.getLogger("agente.storage")


def execute(
    conn: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()
) -> sqlite3.Cursor:
    """Esegue con retry breve e backoff su ``database is locked``."""
    for attempt in range(1, _LOCK_RETRY_ATTEMPTS + 1):
        try:
            return conn.execute(sql, params)
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == _LOCK_RETRY_ATTEMPTS:
                raise StorageError(f"errore SQLite: {exc}") from exc
            time.sleep(_LOCK_RETRY_DELAY_S * attempt)
    raise AssertionError("irraggiungibile")


def commit(conn: sqlite3.Connection) -> None:
    """Commit con conversione esplicita in ``StorageError``.

    Serve ai percorsi di retention: un errore di commit non deve sfuggire come
    ``sqlite3.Error`` (nessun altro layer importa ``sqlite3``).
    """
    try:
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise StorageError(f"commit fallito: {exc}") from exc


class Database:
    """Un solo file SQLite in directory privata, WAL e migrazioni versionate."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._conn: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self.connect()
        return self._conn

    def connect(self) -> sqlite3.Connection:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _chmod(self.path.parent, 0o700)
            conn = sqlite3.connect(self.path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            _chmod(self.path, 0o600)
            return conn
        except (OSError, sqlite3.Error) as exc:
            raise StorageError(f"apertura database fallita: {exc}") from exc

    def migrate(self) -> list[str]:
        """Applica le migrazioni mancanti in ordine; restituisce le versioni."""
        conn = self.connection
        applied: list[str] = []
        try:
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {_SCHEMA_TABLE} ("
                "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            conn.commit()
            done = {
                row["version"]
                for row in conn.execute(f"SELECT version FROM {_SCHEMA_TABLE}")
            }
            for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
                version = migration.stem
                if version in done:
                    continue
                sql = migration.read_text(encoding="utf-8")
                try:
                    conn.executescript(f"BEGIN IMMEDIATE;\n{sql}\nCOMMIT;")
                    conn.execute(
                        f"INSERT INTO {_SCHEMA_TABLE} (version, applied_at) VALUES (?, ?)",
                        (version, _now()),
                    )
                    conn.commit()
                except sqlite3.Error as exc:
                    conn.rollback()
                    raise StorageError(
                        f"migrazione {version} fallita: {exc}"
                    ) from exc
                applied.append(version)
            return applied
        except sqlite3.Error as exc:
            raise StorageError(f"migrazione fallita: {exc}") from exc

    def schema_version(self) -> str | None:
        try:
            row = self.connection.execute(
                f"SELECT version FROM {_SCHEMA_TABLE} ORDER BY version DESC LIMIT 1"
            ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError(f"lettura versione schema fallita: {exc}") from exc
        return None if row is None else str(row["version"])

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connection
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise StorageError(f"transazione annullata: {exc}") from exc
        except BaseException:
            conn.rollback()
            raise

    def execute_with_retry(
        self, sql: str, params: tuple[object, ...] = ()
    ) -> sqlite3.Cursor:
        """Esegue con retry breve e backoff su ``database is locked``."""
        return execute(self.connection, sql, params)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def _chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError as exc:
        logger.warning(
            "permessi non applicabili al filesystem", extra={"path": str(path), "error": str(exc)}
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
