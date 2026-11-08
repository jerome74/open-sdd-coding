"""AC-02: configurazione valida e fatale; nessun segreto nei log."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agente.config import Config, load_config
from agente.errors import ConfigError
from agente.logging_setup import setup_logging

VALID = """
admin_telegram_id = 42
secrets_file = "secrets.env"

[deepseek]
model = "deepseek-flash"
api_base = "https://api.deepseek.test/v1"
max_context_tokens = 8000

[search]
provider = ""

[paths]
db = "{db}"
logs = "{logs}"

[limits]
execution_timeout_s = 600
retry_attempts = 3
retry_delay_s = 60
approval_timeout_s = 900
history_retention_days = 30
chat_memory_hours = 24
battery_threshold_pct = 15
offline_threshold_s = 3600
battery_check_s = 300
liveness_at = "08:00"
"""


def _write(tmp_path: Path, *, text: str | None = None, secrets: str | None) -> Path:
    config_path = tmp_path / "config.toml"
    body = text or VALID.format(db=tmp_path / "agente.db", logs=tmp_path / "logs")
    config_path.write_text(body, encoding="utf-8")
    os.chmod(config_path, 0o600)
    if secrets is not None:
        secret_path = tmp_path / "secrets.env"
        secret_path.write_text(secrets, encoding="utf-8")
        os.chmod(secret_path, 0o600)
    return config_path


def test_loads_valid_config(tmp_path: Path) -> None:
    config_path = _write(tmp_path, secrets="TELEGRAM_TOKEN=tg\nDEEPSEEK_API_KEY=ds\n")
    config = load_config(config_path, env={})

    assert isinstance(config, Config)
    assert config.admin_telegram_id == 42
    assert config.telegram.token == "tg"
    assert config.deepseek.api_key == "ds"
    assert config.deepseek.model == "deepseek-flash"
    assert config.limits.execution_timeout_s == 600
    assert config.limits.approval_timeout_s == 900
    assert config.limits.connectivity_check_s == 60
    assert config.limits.battery_check_s == 300
    assert config.paths.db == tmp_path / "agente.db"


def test_env_secrets_are_used_when_file_absent(tmp_path: Path) -> None:
    text = VALID.format(db=tmp_path / "db", logs=tmp_path / "logs").replace(
        'secrets_file = "secrets.env"\n', ""
    )
    config_path = _write(tmp_path, text=text, secrets=None)
    config = load_config(
        config_path,
        env={"TELEGRAM_TOKEN": "from-env", "DEEPSEEK_API_KEY": "key-env"},
    )
    assert config.telegram.token == "from-env"
    assert config.deepseek.api_key == "key-env"


def test_missing_required_field_is_fatal(tmp_path: Path) -> None:
    text = VALID.format(db=tmp_path / "db", logs=tmp_path / "logs").replace(
        "admin_telegram_id = 42\n", ""
    )
    config_path = _write(
        tmp_path,
        text=text,
        secrets="TELEGRAM_TOKEN=tg\nDEEPSEEK_API_KEY=ds\n",
    )
    with pytest.raises(ConfigError, match="admin_telegram_id"):
        load_config(config_path, env={})


def test_missing_secret_is_fatal_and_does_not_leak_values(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path,
        secrets="TELEGRAM_TOKEN=super-secret-tg\n",
    )
    with pytest.raises(ConfigError) as excinfo:
        load_config(config_path, env={})
    assert "DEEPSEEK_API_KEY" in str(excinfo.value)
    assert "super-secret-tg" not in str(excinfo.value)


def test_open_permissions_on_config_are_rejected(tmp_path: Path) -> None:
    config_path = _write(tmp_path, secrets="TELEGRAM_TOKEN=tg\nDEEPSEEK_API_KEY=ds\n")
    os.chmod(config_path, 0o644)
    with pytest.raises(ConfigError, match="permessi"):
        load_config(config_path, env={})


def test_open_permissions_on_secrets_are_rejected(tmp_path: Path) -> None:
    config_path = _write(tmp_path, secrets="TELEGRAM_TOKEN=tg\nDEEPSEEK_API_KEY=ds\n")
    os.chmod(tmp_path / "secrets.env", 0o640)
    with pytest.raises(ConfigError, match="segreti"):
        load_config(config_path, env={})


def test_invalid_limit_is_fatal(tmp_path: Path) -> None:
    text = VALID.format(db=tmp_path / "db", logs=tmp_path / "logs").replace(
        "retry_attempts = 3", "retry_attempts = 0"
    )
    config_path = _write(tmp_path, text=text, secrets="TELEGRAM_TOKEN=tg\nDEEPSEEK_API_KEY=ds\n")
    with pytest.raises(ConfigError, match="retry_attempts"):
        load_config(config_path, env={})


def test_secrets_are_redacted_in_logs(tmp_path: Path) -> None:
    logger = setup_logging(tmp_path / "logs", console=False)
    logger.info(
        "prova",
        extra={"api_key": "top-secret-value", "telegram_token": "tok-abc-999"},
    )
    for handler in logger.parent.handlers:
        handler.flush()

    log_text = (tmp_path / "logs" / "agente.jsonl").read_text(encoding="utf-8")
    assert "top-secret-value" not in log_text
    assert "tok-abc-999" not in log_text
    assert "***" in log_text


def test_chat_progress_threshold_defaults_to_two_seconds(tmp_path: Path) -> None:
    path = _write(tmp_path, secrets="TELEGRAM_TOKEN=tg\nDEEPSEEK_API_KEY=ds\n")

    config = load_config(path, env={})

    assert config.limits.chat_progress_s == 2


def test_chat_progress_threshold_must_be_positive(tmp_path: Path) -> None:
    body = VALID.format(db=tmp_path / "a.db", logs=tmp_path / "logs") + "chat_progress_s = 0\n"
    path = _write(tmp_path, text=body, secrets="TELEGRAM_TOKEN=tg\nDEEPSEEK_API_KEY=ds\n")

    with pytest.raises(ConfigError):
        load_config(path, env={})


def test_search_provider_defaults_to_tavily(tmp_path: Path) -> None:
    text = VALID.format(db=tmp_path / "db", logs=tmp_path / "logs").replace(
        '[search]\nprovider = ""\n', ""
    )
    config_path = _write(tmp_path, text=text, secrets="TELEGRAM_TOKEN=tg\nDEEPSEEK_API_KEY=ds\n")

    config = load_config(config_path, env={})

    assert config.search.provider == "tavily"


def test_explicit_empty_provider_is_kept(tmp_path: Path) -> None:
    config_path = _write(tmp_path, secrets="TELEGRAM_TOKEN=tg\nDEEPSEEK_API_KEY=ds\n")

    config = load_config(config_path, env={})

    assert config.search.provider == ""


def test_invalid_battery_check_is_rejected(tmp_path: Path) -> None:
    text = VALID.format(db=tmp_path / "db", logs=tmp_path / "logs").replace(
        "battery_check_s = 300", "battery_check_s = 0"
    )
    config_path = _write(tmp_path, text=text, secrets="TELEGRAM_TOKEN=tg\nDEEPSEEK_API_KEY=ds\n")

    with pytest.raises(ConfigError, match="battery_check_s"):
        load_config(config_path, env={})


def test_invalid_liveness_time_is_rejected(tmp_path: Path) -> None:
    for value in ("24:00", "8:5", "08:60", "otto"):
        text = VALID.format(db=tmp_path / "db", logs=tmp_path / "logs").replace(
            'liveness_at = "08:00"', f'liveness_at = "{value}"'
        )
        config_path = _write(
            tmp_path,
            text=text,
            secrets="TELEGRAM_TOKEN=tg\nDEEPSEEK_API_KEY=ds\n",
        )

        with pytest.raises(ConfigError, match="liveness_at"):
            load_config(config_path, env={})
