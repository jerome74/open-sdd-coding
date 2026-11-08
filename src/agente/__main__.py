"""Entry point: ``python -m agente --config <path>``."""

from __future__ import annotations

import argparse
import asyncio

from .app import run
from .config import load_config
from .logging_setup import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente Personale Telegram")
    parser.add_argument(
        "--config",
        default="~/.config/agente/config.toml",
        help="percorso del file TOML di configurazione",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    setup_logging(config.paths.logs)
    asyncio.run(run(config))


if __name__ == "__main__":
    main()
