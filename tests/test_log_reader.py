"""C-29: coda, cartelle, rifiuti e note (spec 07)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from agente.device import MAX_LOG_FILES, DeviceAdapter, PathInfo
from agente.errors import DeviceError, GateError
from agente.gate import MAX_OUTPUT_CHARS
from agente.log_reader import MAX_TOTAL_CHARS, LogReader


@pytest.fixture
def logs(tmp_path: Path) -> Path:
    folder = tmp_path / "logs"
    folder.mkdir()
    return folder


def reader() -> LogReader:
    return LogReader(DeviceAdapter())


def test_file_is_read_with_header_and_text(logs: Path) -> None:
    path = logs / "app.log"
    path.write_text("ERROR connessione persa", encoding="utf-8")

    content = reader().read([str(path)], [str(logs)])

    assert len(content.entries) == 1
    entry = content.entries[0]
    assert entry.text == "ERROR connessione persa"
    assert entry.exists is True and entry.truncated is False
    assert content.refused == ()
    assert f"== {entry.path} (23 byte; coda di 23 caratteri) ==" in content.rendered
    assert "ERROR connessione persa" in content.rendered


def test_missing_file_is_reported(logs: Path) -> None:
    path = logs / "assente.log"

    content = reader().read([str(path)], [str(logs)])

    entry = content.entries[0]
    assert entry.exists is False
    assert entry.note == "file inesistente"
    assert "file inesistente" in content.rendered


def test_empty_file_is_reported(logs: Path) -> None:
    path = logs / "vuoto.log"
    path.write_text("", encoding="utf-8")

    content = reader().read([str(path)], [str(logs)])

    assert content.entries[0].note == "file vuoto"
    assert "file vuoto" in content.rendered


def test_large_file_is_truncated_to_the_tail(logs: Path) -> None:
    path = logs / "grande.log"
    path.write_text("x" * 20_000 + "ULTIMO", encoding="utf-8")

    content = reader().read([str(path)], [str(logs)])

    entry = content.entries[0]
    assert entry.truncated is True
    assert len(entry.text) == 8_000
    assert entry.text.endswith("ULTIMO")
    assert "troncato" in content.rendered


def test_utf8_boundary_is_not_broken(logs: Path) -> None:
    path = logs / "emoji.log"
    path.write_text("😀" * 9_000, encoding="utf-8")

    content = reader().read([str(path)], [str(logs)])

    entry = content.entries[0]
    assert len(entry.text) == 8_000
    assert "\ufffd" not in entry.text
    assert entry.text == "😀" * 8_000


def test_utf8_multibyte_is_not_counted_as_bytes(logs: Path) -> None:
    path = logs / "accenti.log"
    path.write_text("à" * 9_000, encoding="utf-8")

    entry = reader().read([str(path)], [str(logs)]).entries[0]

    assert len(entry.text) == 8_000
    assert entry.text == "à" * 8_000


def test_global_budget_is_respected(logs: Path) -> None:
    for index in range(5):
        (logs / f"f{index}.log").write_text("a" * 8_000, encoding="utf-8")

    content = reader().read([str(logs)], [str(logs)])

    assert len(content.rendered) <= MAX_TOTAL_CHARS
    assert any("limite complessivo raggiunto" in note for note in content.notes)
    assert len(content.entries) < 5


def test_total_budget_matches_the_gate_limit() -> None:
    assert MAX_TOTAL_CHARS == MAX_OUTPUT_CHARS


def test_directory_is_not_recursive_and_reports_subfolders(logs: Path) -> None:
    (logs / "app.log").write_text("errore", encoding="utf-8")
    nested = logs / "archivio"
    nested.mkdir()
    (nested / "vecchio.log").write_text("errore vecchio", encoding="utf-8")

    content = reader().read([str(logs)], [str(logs)])

    assert len(content.entries) == 1
    assert content.entries[0].path.endswith("app.log")
    assert any("sottocartelle ignorate: 1" in note for note in content.notes)


def test_symlinks_are_skipped_and_counted(logs: Path, tmp_path: Path) -> None:
    target = logs / "app.log"
    target.write_text("errore", encoding="utf-8")
    (logs / "link.log").symlink_to(target)

    content = reader().read([str(logs)], [str(logs)])

    assert len(content.entries) == 1
    assert any("symlink ignorati: 1" in note for note in content.notes)


def test_empty_directory_is_reported(logs: Path) -> None:
    content = reader().read([str(logs)], [str(logs)])

    assert content.entries == ()
    assert any("cartella senza file" in note for note in content.notes)


def test_more_than_twenty_files_are_reported(logs: Path) -> None:
    for index in range(MAX_LOG_FILES + 2):
        (logs / f"f{index:02d}.log").write_text("x", encoding="utf-8")

    content = reader().read([str(logs)], [str(logs)])

    assert len(content.entries) == MAX_LOG_FILES
    assert any(
        f"elenco troncato a {MAX_LOG_FILES} file" in note for note in content.notes
    )


def test_jsonl_agent_log_is_passed_as_text(logs: Path) -> None:
    path = logs / "agente.jsonl"
    line = (
        '{"ts": "2026-10-29T08:00:00+0100", "level": "ERROR", '
        '"message": "esecuzione fallita", "task_id": 3}'
    )
    path.write_text(line + "\n", encoding="utf-8")

    entry = reader().read([str(path)], [str(logs)]).entries[0]

    assert line in entry.text


def test_empty_request_is_not_an_error() -> None:
    content = reader().read([], [])

    assert content.entries == () and content.refused == ()
    assert content.notes == ("nessun percorso richiesto",)
    assert content.rendered == "Nessun percorso richiesto."


def test_refused_path_is_not_read(logs: Path, tmp_path: Path) -> None:
    outside = tmp_path / "segreto.log"
    outside.write_text("non deve comparire", encoding="utf-8")

    content = reader().read([str(outside)], [str(logs)])

    assert content.refused == (str(outside),)
    assert content.entries == ()
    assert "PERCORSO NON AUTORIZZATO" in content.rendered
    assert "non deve comparire" not in content.rendered


def test_refusal_does_not_stop_the_allowed_paths(logs: Path, tmp_path: Path) -> None:
    (logs / "app.log").write_text("errore", encoding="utf-8")
    outside = tmp_path / "segreto.log"
    outside.write_text("x", encoding="utf-8")

    content = reader().read([str(outside), str(logs / "app.log")], [str(logs)])

    assert content.refused == (str(outside),)
    assert len(content.entries) == 1
    assert "errore" in content.rendered


class StubDevice:
    def __init__(
        self,
        info: PathInfo | None = None,
        *,
        inspect_error: Exception | None = None,
        tail_error: Exception | None = None,
        list_error: Exception | None = None,
    ) -> None:
        self.info = info
        self.inspect_error = inspect_error
        self.tail_error = tail_error
        self.list_error = list_error

    def inspect_path(self, path, allowlist):
        if self.inspect_error is not None:
            raise self.inspect_error
        assert self.info is not None
        return self.info

    def read_file_tail(self, path, allowlist, *, max_chars):
        if self.tail_error is not None:
            raise self.tail_error
        raise AssertionError("non atteso")

    def list_files(self, directory, allowlist, *, limit=20):
        if self.list_error is not None:
            raise self.list_error
        raise AssertionError("non atteso")


def _info(tmp_path: Path, *, readable: bool, size: int = 10) -> PathInfo:
    return PathInfo(
        path=str(tmp_path / "app.log"),
        exists=True,
        is_file=True,
        is_dir=False,
        size=size,
        readable=readable,
    )


def test_unreadable_file_is_reported(tmp_path: Path) -> None:
    device = StubDevice(_info(tmp_path, readable=False))
    content = LogReader(device).read([str(tmp_path / "app.log")], [str(tmp_path)])

    assert content.entries[0].note == "illeggibile"
    assert any("illeggibile" in note for note in content.notes)


def test_read_error_is_reported_as_a_note(tmp_path: Path) -> None:
    device = StubDevice(_info(tmp_path, readable=True), tail_error=DeviceError("permesso"))
    content = LogReader(device).read([str(tmp_path / "app.log")], [str(tmp_path)])

    assert content.entries[0].note.startswith("illeggibile:")
    assert content.rendered


def test_adapter_gate_error_is_a_note(tmp_path: Path) -> None:
    device = StubDevice(inspect_error=GateError("fuori allowlist"))
    content = LogReader(device).read([str(tmp_path / "app.log")], [str(tmp_path)])

    assert content.refused
    assert any("rifiutato dall'adapter" in note for note in content.notes)


def test_inspect_error_is_reported(tmp_path: Path) -> None:
    device = StubDevice(inspect_error=DeviceError("stat fallita"))
    content = LogReader(device).read([str(tmp_path / "app.log")], [str(tmp_path)])

    assert content.entries[0].note.startswith("illeggibile:")


def test_directory_listing_error_is_reported(tmp_path: Path) -> None:
    info = PathInfo(
        path=str(tmp_path),
        exists=True,
        is_file=False,
        is_dir=True,
        size=0,
        readable=True,
    )
    device = StubDevice(info, list_error=DeviceError("elenco fallito"))
    content = LogReader(device).read([str(tmp_path)], [str(tmp_path)])

    assert any("illeggibile" in note for note in content.notes)


def test_reads_and_refusals_are_logged(logs: Path, tmp_path: Path, caplog) -> None:
    (logs / "app.log").write_text("errore", encoding="utf-8")
    outside = tmp_path / "segreto.log"
    outside.write_text("x", encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="agente.log_reader"):
        reader().read([str(logs / "app.log"), str(outside)], [str(logs)])

    messages = [record.message for record in caplog.records]
    assert "log letto" in messages
    assert "percorso log rifiutato" in messages
    assert "lettura log conclusa" in messages
