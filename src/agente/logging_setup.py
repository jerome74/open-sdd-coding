"""C-13 Logging — JSON line su file applicativo + console, senza segreti."""

from __future__ import annotations

import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

SENSITIVE_MARKERS = ("token", "api_key", "apikey", "secret", "password")
REDACTED = "***"


class JsonLineFormatter(logging.Formatter):
    """Una riga JSON per record; campi sensibili oscurati."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = REDACTED if _is_sensitive(key) else value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_RESERVED = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
}


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_MARKERS)


def setup_logging(
    log_dir: str | Path,
    *,
    level: int = logging.INFO,
    filename: str = "agente.jsonl",
    max_bytes: int = 2_000_000,
    backup_count: int = 5,
    console: bool = True,
) -> logging.Logger:
    """Configura il logger radice una sola volta e restituisce il logger app."""
    directory = Path(log_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / filename

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, "_agente", False):
            root.removeHandler(handler)
            handler.close()

    file_handler = RotatingFileHandler(
        log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(JsonLineFormatter())
    file_handler._agente = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(JsonLineFormatter())
        console_handler._agente = True  # type: ignore[attr-defined]
        root.addHandler(console_handler)

    try:
        os.chmod(log_path, 0o600)
    except OSError as exc:
        logging.getLogger("agente.logging").warning(
            "permessi non applicabili al log",
            extra={"path": str(log_path), "error": str(exc)},
        )
    return logging.getLogger("agente")
