"""C-30: autorizzazione dei percorsi di log (spec 07, BR-13)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from agente.log_allowlist import AllowlistValidator, is_within, normalize_path
from agente.storage.repositories import Task


def task(*paths: str) -> Task:
    return Task(
        name="log",
        instructions="riassumi i log",
        schedule_type="orario",
        schedule_expr="08:00",
        log_allowlist=list(paths),
    )


@pytest.fixture
def logs(tmp_path: Path) -> Path:
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "app.log").write_text("errore", encoding="utf-8")
    return folder


def test_file_inside_an_allowed_folder_is_allowed(logs: Path) -> None:
    validator = AllowlistValidator()

    assert validator.is_allowed(logs / "app.log", task(str(logs))) is True


def test_the_allowed_file_itself_is_allowed(logs: Path) -> None:
    validator = AllowlistValidator()

    assert validator.is_allowed(str(logs / "app.log"), task(str(logs / "app.log"))) is True


def test_path_outside_the_allowlist_is_refused(logs: Path, tmp_path: Path) -> None:
    validator = AllowlistValidator()

    assert validator.is_allowed(tmp_path / "altro.log", task(str(logs))) is False


def test_sibling_with_a_common_prefix_is_refused(logs: Path) -> None:
    sibling = logs.parent / "logs-altro"
    sibling.mkdir()
    (sibling / "app.log").write_text("x", encoding="utf-8")

    assert AllowlistValidator().is_allowed(sibling / "app.log", task(str(logs))) is False


def test_traversal_is_refused(logs: Path) -> None:
    escape = f"{logs}/../segreto.log"

    assert AllowlistValidator().is_allowed(escape, task(str(logs))) is False


def test_symlink_escape_is_refused(logs: Path, tmp_path: Path) -> None:
    secret = tmp_path / "segreto.log"
    secret.write_text("x", encoding="utf-8")
    link = logs / "link.log"
    link.symlink_to(secret)

    assert AllowlistValidator().is_allowed(link, task(str(logs))) is False


def test_relative_path_is_refused(logs: Path) -> None:
    assert AllowlistValidator().is_allowed("logs/app.log", task(str(logs))) is False


def test_home_prefix_is_expanded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "app.log").write_text("x", encoding="utf-8")

    assert AllowlistValidator().is_allowed("~/logs/app.log", task("~/logs")) is True


def test_empty_path_is_refused(logs: Path) -> None:
    assert AllowlistValidator().is_allowed("   ", task(str(logs))) is False


def test_empty_allowlist_refuses_everything(logs: Path) -> None:
    assert AllowlistValidator().is_allowed(logs / "app.log", task()) is False


def test_disallowed_task_object_without_allowlist_is_refused(logs: Path) -> None:
    class Bare:
        pass

    assert AllowlistValidator().is_allowed(logs / "app.log", Bare()) is False


def test_invalid_allowlist_entries_are_ignored(logs: Path) -> None:
    assert AllowlistValidator().is_allowed(logs / "app.log", task("", "logs", str(logs))) is True


def test_validation_is_logged(logs: Path, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="agente.log_allowlist"):
        AllowlistValidator().is_allowed(logs / "app.log", task(str(logs)))

    record = next(r for r in caplog.records if r.message == "validazione percorso log")
    assert record.allowed is True
    assert record.roots == 1


def test_normalize_and_within_helpers(tmp_path: Path) -> None:
    root = tmp_path / "logs"
    root.mkdir()
    child = root / "a.log"
    child.write_text("x", encoding="utf-8")

    normalized = normalize_path(child)
    assert normalized == child.resolve()
    assert normalize_path("  ") is None
    assert is_within(child.resolve(), root.resolve()) is True
    assert is_within(tmp_path.resolve(), root.resolve()) is False
