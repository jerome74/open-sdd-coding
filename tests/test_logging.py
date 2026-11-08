"""C-13: log JSON line, rotazione configurata, nessun segreto."""

from __future__ import annotations

import json
from pathlib import Path

from agente.logging_setup import setup_logging


def test_log_is_one_json_object_per_line(tmp_path: Path) -> None:
    logger = setup_logging(tmp_path / "logs", console=False)
    logger.info("primo", extra={"task_id": 7})
    logger.info("secondo")
    for handler in logger.parent.handlers:
        handler.flush()

    lines = (tmp_path / "logs" / "agente.jsonl").read_text(encoding="utf-8").splitlines()
    payloads = [json.loads(line) for line in lines]
    assert payloads[0]["message"] == "primo"
    assert payloads[0]["task_id"] == 7
    assert payloads[0]["level"] == "INFO"
    assert payloads[1]["message"] == "secondo"


def test_log_file_is_private(tmp_path: Path) -> None:
    setup_logging(tmp_path / "logs", console=False)
    mode = (tmp_path / "logs" / "agente.jsonl").stat().st_mode & 0o777
    assert mode & 0o077 == 0


def test_handlers_are_not_duplicated(tmp_path: Path) -> None:
    first = setup_logging(tmp_path / "logs", console=False)
    second = setup_logging(tmp_path / "logs", console=False)
    handlers = [h for h in second.parent.handlers if getattr(h, "_agente", False)]
    assert len(handlers) == 1
    assert first.name == second.name == "agente"
