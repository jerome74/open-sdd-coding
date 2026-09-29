#!/usr/bin/env python3
"""Read-only publication gate for the knowledge bundle (wiki + semantic index).

Decides whether publishing may proceed or must first ask the operator to confirm overwriting an
existing index in the destination (BR-5). It performs **no** write and **no** push: it only inspects
the configured destination (remote, branch, paths) inside the local git repository.

Destination comes from ``knowledge-config.json`` (``publication``): ``remote``, ``branch_pattern``
(with a ``{name}`` placeholder) and the published ``paths``. The branch inspected is
``branch_pattern`` with ``{name}`` replaced by the project/repository name.

Usage
    python3 scripts/publish_gate.py <name> [--config PATH] [--repo-root .]

Output: JSON {"branch", "remote", "ref", "index_path", "exists", "decision"}.
Exit codes
    0  proceed          — no existing index in the destination
    1  confirm-required — an index already exists; ask the operator before overwriting
    2  error            — invalid config, not a git repo, or the configured remote is missing
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_CONFIG = "knowledge-config.json"
DEFAULT_PUBLICATION = {
    "remote": "origin",
    "branch_pattern": "{name}_llm_wiki",
    "paths": ["graphify-out", "index"],
}

EXIT_PROCEED, EXIT_CONFIRM, EXIT_ERROR = 0, 1, 2


class GateError(Exception):
    """Fatal gate condition (exit code 2)."""


def load_config(config_path: Path) -> dict:
    if not config_path.is_file():
        raise GateError(f"config not found: {config_path}")
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateError(f"config is not valid JSON: {config_path}: {exc}") from exc


def _git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=False
    )


def resolve_branch(pattern: str, name: str) -> str:
    return pattern.replace("{name}", name)


def remote_exists(repo_root: Path, remote: str) -> bool:
    result = _git(repo_root, ["remote"])
    return result.returncode == 0 and remote in result.stdout.split()


def find_ref(repo_root: Path, remote: str, branch: str) -> str | None:
    """Prefer the remote-tracking ref, fall back to the local branch."""
    for ref in (f"{remote}/{branch}", f"refs/heads/{branch}"):
        if _git(repo_root, ["rev-parse", "--verify", "--quiet", ref]).returncode == 0:
            return ref
    return None


def ref_has_path(repo_root: Path, ref: str, path: str) -> bool:
    result = _git(repo_root, ["ls-tree", "-r", "--name-only", ref, "--", path])
    return result.returncode == 0 and bool(result.stdout.strip())


def evaluate(config: dict, name: str, repo_root: Path) -> dict:
    publication = {**DEFAULT_PUBLICATION, **config.get("publication", {})}
    remote = publication["remote"]
    branch = resolve_branch(publication["branch_pattern"], name)

    semantic_index = config.get("semantic_index")
    if not semantic_index:
        raise GateError("config is missing 'semantic_index'")
    index_dir = Path(semantic_index).parent.as_posix()
    paths = list(publication.get("paths") or [])
    if index_dir not in paths:
        paths.append(index_dir)

    if not remote_exists(repo_root, remote):
        raise GateError(f"git remote {remote!r} not found in {repo_root}")

    ref = find_ref(repo_root, remote, branch)
    presence = {path: bool(ref) and ref_has_path(repo_root, ref, path) for path in paths}
    return {
        "branch": branch,
        "remote": remote,
        "ref": ref,
        "index_path": index_dir,
        "paths": presence,
        "exists": presence[index_dir],
        "decision": "confirm-required" if presence[index_dir] else "proceed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only publication overwrite gate (BR-5).")
    parser.add_argument("name", help="project/repository name (fills {name} in branch_pattern)")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"config path (default {DEFAULT_CONFIG})")
    parser.add_argument("--repo-root", default=".", help="repository root (default .)")
    args = parser.parse_args(argv)

    try:
        config = load_config(Path(args.config))
        result = evaluate(config, args.name, Path(args.repo_root).resolve())
    except GateError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return EXIT_ERROR

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_CONFIRM if result["exists"] else EXIT_PROCEED


if __name__ == "__main__":
    raise SystemExit(main())
