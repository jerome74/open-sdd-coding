#!/usr/bin/env python3
"""Select the single active knowledge base by rewriting pointer keys.

Only graph_json, bundle_root and semantic_index are rewritten in the default
knowledge-config.json; the rest of the file is preserved byte for byte.
The inactive knowledge base stays reachable with an explicit --config.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "knowledge-config.json"
STATE_FILE = REPO_ROOT / ".kb-active.json"
POINTER_KEYS = ("graph_json", "bundle_root", "semantic_index")
CONFIGS = {
    "graphify": DEFAULT_CONFIG,
    "compass": REPO_ROOT / "knowledge-config.compass.json",
}


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def pointers(config: dict) -> dict:
    return {key: config[key] for key in POINTER_KEYS}


def read_state() -> dict:
    if not STATE_FILE.exists():
        return {"active": None, "profiles": {}}
    return load_json(STATE_FILE)


def write_state(state: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(REPO_ROOT), prefix=".kb-active.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, STATE_FILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def ensure_state() -> dict:
    state = read_state()
    profiles = state.setdefault("profiles", {})
    active = state.get("active")
    if not profiles.get("graphify"):
        if active == "compass":
            raise RuntimeError(
                "state is missing the graphify profile and compass is active; run "
                "`kb_active.py set graphify` with an explicit profile or restore the state file"
            )
        profiles["graphify"] = pointers(load_json(DEFAULT_CONFIG))
    if not profiles.get("compass"):
        profiles["compass"] = pointers(load_json(CONFIGS["compass"]))
    return state


def target_problems(values: dict) -> list:
    problems = []
    graph = REPO_ROOT / values["graph_json"]
    bundle = REPO_ROOT / values["bundle_root"]
    index = REPO_ROOT / values["semantic_index"]
    if not graph.is_file():
        problems.append(f"graph_json not found: {values['graph_json']}")
    if not bundle.is_dir():
        problems.append(f"bundle_root not found: {values['bundle_root']}")
    if not index.is_file():
        problems.append(f"semantic_index not found: {values['semantic_index']}")
    return problems


def rewrite_pointers(values: dict, dry_run: bool) -> None:
    text = DEFAULT_CONFIG.read_text(encoding="utf-8")
    updated = text
    for key in POINTER_KEYS:
        pattern = re.compile(rf'(?m)^(\s*"{re.escape(key)}"\s*:\s*)"[^"]*"')
        matches = pattern.findall(updated)
        if len(matches) != 1:
            raise RuntimeError(f"expected exactly one pointer key {key!r}, found {len(matches)}")
        updated = pattern.sub(
            lambda match, value=values[key]: f'{match.group(1)}"{value}"',
            updated,
            count=1,
        )
    parsed = json.loads(updated)
    for key in POINTER_KEYS:
        if parsed.get(key) != values[key]:
            raise RuntimeError(f"pointer rewrite failed for {key!r}")
    if dry_run:
        print(f"dry-run: would set {', '.join(f'{k}={values[k]}' for k in POINTER_KEYS)}")
        return
    backup = DEFAULT_CONFIG.with_name(DEFAULT_CONFIG.name + ".bak")
    shutil.copy2(DEFAULT_CONFIG, backup)
    fd, tmp = tempfile.mkstemp(dir=str(REPO_ROOT), prefix=".knowledge-config.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(updated)
        os.replace(tmp, DEFAULT_CONFIG)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def cmd_status(args: argparse.Namespace) -> int:
    state = ensure_state()
    values = pointers(load_json(DEFAULT_CONFIG))
    if state.get("active"):
        active = state["active"]
    else:
        active = "graphify" if values["graph_json"].startswith("graphify-out") else "unknown"
    if args.json:
        print(json.dumps({"active": active, "pointers": values, "profiles": state["profiles"]}, indent=2))
        return 0
    print(f"active: {active}")
    for key in POINTER_KEYS:
        print(f"  {key}: {values[key]}")
    for name, profile in sorted(state["profiles"].items()):
        print(f"profile {name}: {profile['graph_json']} | {profile['bundle_root']} | {profile['semantic_index']}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    if not CONFIGS[args.kb].is_file():
        print(f"error: config not found: {CONFIGS[args.kb].relative_to(REPO_ROOT)}", file=sys.stderr)
        return 3
    try:
        state = ensure_state()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    values = dict(state["profiles"][args.kb])
    problems = target_problems(values)
    if problems and not args.force:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        print("refusing to point the active KB at missing artifacts (use --force to override)", file=sys.stderr)
        return 2
    rewrite_pointers(values, args.dry_run)
    if not args.dry_run:
        state["active"] = args.kb
        write_state(state)
        print(f"active knowledge base: {args.kb}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="show the active knowledge base and pointers")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    set_cmd = sub.add_parser("set", help="point the default config at one knowledge base")
    set_cmd.add_argument("kb", choices=sorted(CONFIGS))
    set_cmd.add_argument("--dry-run", action="store_true")
    set_cmd.add_argument("--force", action="store_true", help="skip target existence checks")
    set_cmd.set_defaults(func=cmd_set)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
