#!/usr/bin/env python3
"""Deterministic pre-flight change detection for the graph-first knowledge pipeline.

Walks the configured `source_roots`, hashes every non-ignored file, and compares the result
with the stored `source_manifest`. Reports, per root, which files were added, modified, or
deleted since the last sealed build. Stdlib-only, no dependencies, no network, no LLM call.

Interface
    python3 scripts/source_watch.py                 # human-readable report
    python3 scripts/source_watch.py --json          # machine-readable (for the agent)
    python3 scripts/source_watch.py --update        # seal the current state after a build
    python3 scripts/source_watch.py --root src      # limit to one root
    python3 scripts/source_watch.py --config PATH    # default knowledge-config.json

Exit codes
    0  no changes
    1  changes detected
    2  error (missing/invalid config, corrupt manifest, unreadable root)

The manifest is anchored to the SHA-256 of file *content*, not mtime: a `git checkout` that
restores identical files produces no false positive.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_VERSION = 1
DEFAULT_CONFIG = "knowledge-config.json"
# Directories never walked, regardless of .gitignore.
SKIP_DIRS = {".git", ".obsidian", ".svn", ".hg", "__pycache__", "node_modules", ".DS_Store"}
EXIT_NO_CHANGE, EXIT_CHANGED, EXIT_ERROR = 0, 1, 2


class WatchError(Exception):
    """Fatal, exit-code-2 condition."""


def load_config(config_path: Path) -> dict:
    if not config_path.is_file():
        raise WatchError(f"config not found: {config_path}")
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WatchError(f"config is not valid JSON: {config_path}: {exc}") from exc


def load_gitignore_patterns(repo_root: Path) -> list[str]:
    """Best-effort .gitignore support: read the root .gitignore into fnmatch patterns.

    Not a full gitignore implementation — matches basename and posix relative path against
    each non-negated, non-comment pattern. Enough to keep build artifacts out of the manifest.
    """
    gitignore = repo_root / ".gitignore"
    if not gitignore.is_file():
        return []
    patterns: list[str] = []
    for line in gitignore.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        patterns.append(line.rstrip("/"))
    return patterns


def is_gitignored(rel_posix: str, name: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel_posix, pat) or fnmatch.fnmatch(
            rel_posix, f"*/{pat}"
        ):
            return True
    return False


def sha256_of(path: Path) -> str:
    """Streaming SHA-256 — never loads the whole file into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def fingerprint_root(
    repo_root: Path, root: str, ignored_files: set[str], gitignore: list[str]
) -> dict[str, str]:
    """Map of {relative-posix-path -> content hash} for every tracked file under `root`."""
    root_dir = repo_root / root
    result: dict[str, str] = {}
    if not root_dir.exists():
        return result  # non-existent root: handled by the caller as a warning, not an error
    for path in sorted(root_dir.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root_dir).parts):
            continue
        if path.name in ignored_files:
            continue
        rel_to_root = path.relative_to(root_dir).as_posix()
        rel_to_repo = path.relative_to(repo_root).as_posix()
        if gitignore and is_gitignored(rel_to_repo, path.name, gitignore):
            continue
        result[rel_to_root] = sha256_of(path)
    return result


def diff_root(current: dict[str, str], previous: dict[str, str]) -> dict[str, list[str]]:
    added = sorted(p for p in current if p not in previous)
    deleted = sorted(p for p in previous if p not in current)
    modified = sorted(p for p in current if p in previous and current[p] != previous[p])
    return {"added": added, "modified": modified, "deleted": deleted}


def build_report(
    repo_root: Path, config: dict, only_root: str | None
) -> tuple[dict, dict[str, dict[str, str]], list[str]]:
    roots = config.get("source_roots", [])
    if only_root is not None:
        if only_root not in roots:
            raise WatchError(f"--root {only_root!r} is not in source_roots: {roots}")
        roots = [only_root]
    ignored_files = set(config.get("source_ignored_files", []))
    gitignore = load_gitignore_patterns(repo_root)

    manifest_path = repo_root / config["source_manifest"]
    previous_roots: dict[str, dict[str, str]] = {}
    if manifest_path.is_file():
        try:
            previous_roots = json.loads(manifest_path.read_text(encoding="utf-8")).get("roots", {})
        except json.JSONDecodeError as exc:
            raise WatchError(f"manifest is corrupt: {manifest_path}: {exc}") from exc

    current_roots: dict[str, dict[str, str]] = {}
    per_root_diff: dict[str, dict[str, list[str]]] = {}
    warnings: list[str] = []
    for root in roots:
        if not (repo_root / root).exists():
            warnings.append(f"configured root does not exist, skipped: {root}")
        current = fingerprint_root(repo_root, root, ignored_files, gitignore)
        current_roots[root] = current
        per_root_diff[root] = diff_root(current, previous_roots.get(root, {}))

    changed_roots = [r for r, d in per_root_diff.items() if d["added"] or d["modified"] or d["deleted"]]
    totals = {
        "added": sum(len(d["added"]) for d in per_root_diff.values()),
        "modified": sum(len(d["modified"]) for d in per_root_diff.values()),
        "deleted": sum(len(d["deleted"]) for d in per_root_diff.values()),
    }
    report = {
        "changed": bool(changed_roots),
        "roots": per_root_diff,
        "changed_roots": changed_roots,
        "totals": totals,
    }
    return report, current_roots, warnings


def write_manifest(repo_root: Path, config: dict, current_roots: dict[str, dict[str, str]]) -> None:
    manifest_path = repo_root / config["source_manifest"]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve unscanned roots (e.g. when --root limited the scan) from the old manifest.
    roots = dict(current_roots)
    if manifest_path.is_file():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8")).get("roots", {})
            for name, files in old.items():
                roots.setdefault(name, files)
        except json.JSONDecodeError:
            pass
    payload = {
        "version": MANIFEST_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roots": roots,
    }
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def print_human(report: dict, warnings: list[str], sealed: bool) -> None:
    for warning in warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    for root, diff in report["roots"].items():
        counts = f"+{len(diff['added'])} ~{len(diff['modified'])} -{len(diff['deleted'])}"
        print(f"{root:<14} {counts}")
        for kind, mark in (("added", "+"), ("modified", "~"), ("deleted", "-")):
            for rel in diff[kind]:
                print(f"    {mark} {rel}")
    t = report["totals"]
    print(f"\ntotal: +{t['added']} ~{t['modified']} -{t['deleted']}   changed_roots: {report['changed_roots']}")
    if sealed:
        print("manifest sealed.")
    elif not report["changed"]:
        print("no changes since the last sealed build.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect source changes for the knowledge pipeline.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--update", action="store_true", help="seal the current state (after a build)")
    parser.add_argument("--root", metavar="ROOT", help="limit to a single configured source root")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"config path (default {DEFAULT_CONFIG})")
    parser.add_argument("--repo-root", default=".", help="repository root (default .)")
    args = parser.parse_args(argv)

    try:
        repo_root = Path(args.repo_root).resolve()
        config = load_config(repo_root / args.config)
        report, current_roots, warnings = build_report(repo_root, config, args.root)

        if args.update:
            write_manifest(repo_root, config, current_roots)

        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print_human(report, warnings, sealed=args.update)
    except WatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR

    # --update always seals successfully; report exit reflects whether a build is needed.
    if args.update:
        return EXIT_NO_CHANGE
    return EXIT_CHANGED if report["changed"] else EXIT_NO_CHANGE


if __name__ == "__main__":
    raise SystemExit(main())
