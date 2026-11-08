"""Confini di integrazione della constitution: un solo punto di accesso per esterno."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "agente"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def _modules() -> list[Path]:
    return sorted(path for path in SRC.rglob("*.py") if "__pycache__" not in path.parts)


def test_telegram_is_imported_only_by_the_gateway() -> None:
    offenders = [
        path.name
        for path in _modules()
        if "telegram" in _imports(path) and path.name != "telegram_gateway.py"
    ]
    assert offenders == []


def test_sqlite_is_imported_only_by_storage() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in _modules()
        if "sqlite3" in _imports(path) and path.parent.name != "storage"
    ]
    assert offenders == []


def test_subprocess_is_imported_only_by_the_device_adapter() -> None:
    offenders = [
        path.name
        for path in _modules()
        if "subprocess" in _imports(path) and path.name != "device.py"
    ]
    assert offenders == []


def test_http_clients_are_confined_to_their_adapters() -> None:
    # Spec 06: C-26 è il secondo client HTTP dichiarato (provider di ricerca).
    allowed = {"llm.py", "web_search.py"}
    offenders = [
        path.name
        for path in _modules()
        if "httpx" in _imports(path) and path.name not in allowed
    ]
    assert offenders == []


def test_apscheduler_is_imported_only_by_the_scheduler() -> None:
    offenders = [
        path.name
        for path in _modules()
        if "apscheduler" in _imports(path) and path.name != "scheduler.py"
    ]
    assert offenders == []



_FILESYSTEM_CALLS = {
    "open",
    "read_text",
    "read_bytes",
    "write_text",
    "iterdir",
    "scandir",
    "stat",
    "unlink",
}


def test_log_modules_do_not_access_the_filesystem() -> None:
    offenders: dict[str, list[str]] = {}
    for name in ("log_reader.py", "log_allowlist.py"):
        tree = ast.parse((SRC / name).read_text(encoding="utf-8"))
        called: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
        bad = sorted(called & _FILESYSTEM_CALLS)
        if bad:
            offenders[name] = bad
    assert offenders == {}
