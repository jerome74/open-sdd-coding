"""AC-03: risoluzione del ruolo e permessi."""

from __future__ import annotations

from agente.role_guard import Role, RoleGuard, admin_only, authorized_or_admin
from agente.storage.db import Database
from agente.storage.repositories import User, repositories


def _guard(make_config, tmp_path):
    db = Database(tmp_path / "ruoli.db")
    db.migrate()
    repos = repositories(db.connection)
    repos.users.upsert(User(telegram_id=2, state="accepted"))
    repos.users.upsert(User(telegram_id=3, state="pending"))
    repos.users.upsert(User(telegram_id=4, state="revoked"))
    config = make_config(admin_id=1)
    return RoleGuard(config, repos.users), db


def test_admin_comes_only_from_config(make_config, tmp_path) -> None:
    guard, db = _guard(make_config, tmp_path)
    assert guard.resolve_role(1) is Role.ADMIN
    assert guard.resolve_role(2) is Role.AUTHORIZED
    assert guard.resolve_role(3) is Role.UNKNOWN
    assert guard.resolve_role(4) is Role.UNKNOWN
    assert guard.resolve_role(999) is Role.UNKNOWN
    db.close()


def test_decorators_apply_permissions(make_config, tmp_path) -> None:
    guard, db = _guard(make_config, tmp_path)
    seen: list[int] = []

    @admin_only(guard)
    def solo_admin(telegram_id: int) -> str:
        seen.append(telegram_id)
        return "ok"

    @authorized_or_admin(guard)
    def tutti_gli_autorizzati(telegram_id: int) -> str:
        seen.append(telegram_id)
        return "ok"

    assert solo_admin(1) == "ok"
    assert solo_admin(2) is None
    assert tutti_gli_autorizzati(2) == "ok"
    assert tutti_gli_autorizzati(3) is None
    assert tutti_gli_autorizzati(4) is None
    assert seen == [1, 2]
    db.close()


def test_pending_and_revoked_are_unknown(make_config, tmp_path) -> None:
    guard, db = _guard(make_config, tmp_path)

    assert guard.resolve_role(3) is Role.UNKNOWN
    assert guard.resolve_role(4) is Role.UNKNOWN
    db.close()
