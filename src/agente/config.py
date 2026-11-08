"""C-01 Config Loader — configurazione immutabile e tipizzata.

Formato: TOML per i parametri non segreti; segreti da file ``KEY=VALUE``
(``chmod 600``) o variabili d'ambiente. Le chiavi attese sono elencate da spec
01 C-01.

Assunzione (piano 01): ``search`` è opzionale finché spec 06 non introduce il
provider; ``deepseek.api_base`` e ``max_context_tokens`` sono obbligatori
perché la spec non dichiara un default.
"""

from __future__ import annotations

import os
import re
import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .errors import ConfigError

DEFAULT_MODEL = "deepseek-flash"

REQUIRED_SECRETS = ("TELEGRAM_TOKEN", "DEEPSEEK_API_KEY")


@dataclass(frozen=True)
class TelegramConfig:
    token: str


@dataclass(frozen=True)
class DeepSeekConfig:
    model: str
    api_base: str
    api_key: str
    max_context_tokens: int


@dataclass(frozen=True)
class SearchConfig:
    provider: str = ""
    api_key: str = ""


@dataclass(frozen=True)
class PathsConfig:
    db: Path
    logs: Path


@dataclass(frozen=True)
class LimitsConfig:
    execution_timeout_s: int = 600
    retry_attempts: int = 3
    retry_delay_s: int = 60
    approval_timeout_s: int = 900
    history_retention_days: int = 30
    chat_memory_hours: int = 24
    battery_threshold_pct: int = 15
    offline_threshold_s: int = 3600
    liveness_at: str = "08:00"
    min_interval_minutes: int = 1
    connectivity_check_s: int = 60
    battery_check_s: int = 300
    chat_progress_s: int = 2


@dataclass(frozen=True)
class Config:
    admin_telegram_id: int
    telegram: TelegramConfig
    deepseek: DeepSeekConfig
    search: SearchConfig
    paths: PathsConfig
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    source: Path | None = None


def load_config(
    path: str | Path,
    *,
    env: Mapping[str, str] | None = None,
) -> Config:
    """Carica e valida la configurazione.

    Un campo obbligatorio mancante, un segreto illeggibile o un permesso non
    privato producono :class:`ConfigError` e nessuna configurazione parziale.
    I valori dei segreti non compaiono mai nei messaggi di errore.
    """
    config_path = Path(path).expanduser()
    env = os.environ if env is None else env

    if not config_path.is_file():
        raise ConfigError(f"file di configurazione non trovato: {config_path}")
    _require_private_file(config_path, "configurazione")

    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML non valido in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"configurazione illeggibile: {exc}") from exc

    secrets = _load_secrets(raw, config_path, env)
    admin_id = _require_int(raw, "admin_telegram_id", "admin_telegram_id")

    deepseek_raw = _require_table(raw, "deepseek")
    paths_raw = _require_table(raw, "paths")

    token = secrets.get("TELEGRAM_TOKEN", "")
    if not token:
        raise ConfigError("segreto mancante: TELEGRAM_TOKEN")
    api_key = secrets.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ConfigError("segreto mancante: DEEPSEEK_API_KEY")

    model = _optional_str(deepseek_raw, "model", DEFAULT_MODEL) or DEFAULT_MODEL
    api_base = _optional_str(deepseek_raw, "api_base")
    if not api_base:
        raise ConfigError("campo obbligatorio mancante: deepseek.api_base")
    max_context = deepseek_raw.get("max_context_tokens")
    if not isinstance(max_context, int) or max_context <= 0:
        raise ConfigError(
            "campo obbligatorio mancante o non valido: deepseek.max_context_tokens"
        )

    search_raw = raw.get("search", {})
    if not isinstance(search_raw, dict):
        raise ConfigError("sezione non valida: search")
    search = SearchConfig(
        # D2 (spec 06): Tavily è il default; un provider="" esplicito resta vuoto.
        provider=_optional_str(search_raw, "provider", "tavily"),
        api_key=secrets.get("SEARCH_API_KEY", ""),
    )

    db_path = _require_path(paths_raw, "db", "paths.db")
    logs_path = _require_path(paths_raw, "logs", "paths.logs")

    limits = _load_limits(raw.get("limits", {}))

    return Config(
        admin_telegram_id=admin_id,
        telegram=TelegramConfig(token=token),
        deepseek=DeepSeekConfig(
            model=model,
            api_base=api_base,
            api_key=api_key,
            max_context_tokens=max_context,
        ),
        search=search,
        paths=PathsConfig(db=db_path, logs=logs_path),
        limits=limits,
        source=config_path,
    )


def _load_secrets(
    raw: Mapping[str, Any],
    config_path: Path,
    env: Mapping[str, str],
) -> dict[str, str]:
    secrets_file: str | None = raw.get("secrets_file")
    secrets: dict[str, str] = {}
    if secrets_file:
        secret_path = _resolve_path(secrets_file, config_path)
        if not secret_path.is_file():
            raise ConfigError(f"file dei segreti non trovato: {secret_path}")
        _require_private_file(secret_path, "segreti")
        try:
            for line in secret_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                secrets[key.strip()] = value.strip().strip('"').strip("'")
        except OSError as exc:
            raise ConfigError(f"segreti illeggibili: {exc}") from exc
    for key in REQUIRED_SECRETS + ("SEARCH_API_KEY",):
        if not secrets.get(key) and env.get(key):
            secrets[key] = env[key]
    return secrets


def _load_limits(raw: Any) -> LimitsConfig:
    if not isinstance(raw, dict):
        raise ConfigError("sezione non valida: limits")
    defaults = LimitsConfig()
    values: dict[str, Any] = {}
    for name in (
        "execution_timeout_s",
        "retry_attempts",
        "retry_delay_s",
        "approval_timeout_s",
        "history_retention_days",
        "chat_memory_hours",
        "battery_threshold_pct",
        "offline_threshold_s",
        "min_interval_minutes",
        "connectivity_check_s",
        "battery_check_s",
        "chat_progress_s",
    ):
        value = raw.get(name, getattr(defaults, name))
        if not isinstance(value, int) or value <= 0:
            raise ConfigError(f"limite non valido: limits.{name}")
        values[name] = value
    liveness = raw.get("liveness_at", defaults.liveness_at)
    if not isinstance(liveness, str) or re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d", liveness
    ) is None:
        raise ConfigError("limite non valido: limits.liveness_at")
    values["liveness_at"] = liveness
    return LimitsConfig(**values)


def _require_table(raw: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"sezione obbligatoria mancante: {name}")
    return value


def _require_int(raw: Mapping[str, Any], name: str, label: str) -> int:
    value = raw.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"campo obbligatorio mancante o non valido: {label}")
    return value


def _optional_str(raw: Mapping[str, Any], name: str, default: str = "") -> str:
    value = raw.get(name, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ConfigError(f"campo non valido: {name}")
    return value.strip()


def _require_path(raw: Mapping[str, Any], name: str, label: str) -> Path:
    value = raw.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"campo obbligatorio mancante: {label}")
    return Path(value).expanduser()


def _resolve_path(value: str, config_path: Path) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate
    return (config_path.parent / candidate).resolve()


def _require_private_file(path: Path, label: str) -> None:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise ConfigError(f"{label} non accessibile: {exc}") from exc
    if mode & 0o077:
        raise ConfigError(
            f"{label} con permessi troppo aperti ({oct(mode)}): richiesto 600"
        )
