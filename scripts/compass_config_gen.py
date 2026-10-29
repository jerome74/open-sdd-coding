#!/usr/bin/env python3
"""Generate .compass/config.toml from knowledge-config.compass.json."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "knowledge-config.compass.json"


def render(config: dict) -> str:
    build = config.get("compass_build", {})
    include = build.get("include") or [f"{root.rstrip('/')}/" for root in config["source_roots"]]
    include = [path if path.endswith("/") else f"{path}/" for path in include]
    exclude = build.get("exclude") or []
    lines = [
        "version = 1",
        "",
        "[build]",
        f"include = {json.dumps(include)}",
        f"exclude = {json.dumps(exclude)}",
        "",
    ]
    return "\n".join(lines)


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--stdout", action="store_true")
    parser.add_argument("--check", action="store_true", help="exit 1 if the generated file is stale")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (REPO_ROOT / config_path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))

    target = config.get("compass_build", {}).get("config_file", ".compass/config.toml")
    target_path = REPO_ROOT / target
    rendered = render(config)

    if args.stdout:
        print(rendered, end="")
        return 0

    current = target_path.read_text(encoding="utf-8") if target_path.exists() else None
    if args.check:
        if current != rendered:
            print(f"stale: {target}", file=sys.stderr)
            return 1
        print(f"ok: {target}")
        return 0

    if current == rendered:
        print(f"unchanged: {target}")
        return 0
    write_atomic(target_path, rendered)
    print(f"wrote: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
