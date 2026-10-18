"""Run report shared by the CLI and the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Report:
    counts: dict[str, int] = field(
        default_factory=lambda: {"total": 0, "converted": 0, "skipped": 0, "errors": 0}
    )
    errors: list[dict[str, Any]] = field(default_factory=list)
    roots: list[Path] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "error" if self.counts["errors"] else "ok"

    def count(self, key: str, amount: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + amount

    def add_error(self, root: Path, file: str, error: str) -> None:
        self.errors.append({"root": str(root), "file": file, "error": error})
        self.count("errors")

    def merge(self, other: "Report") -> None:
        for key, value in other.counts.items():
            self.count(key, value)
        self.errors.extend(other.errors)
        self.roots.extend(other.roots)

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "counts": dict(self.counts), "errors": list(self.errors)}
