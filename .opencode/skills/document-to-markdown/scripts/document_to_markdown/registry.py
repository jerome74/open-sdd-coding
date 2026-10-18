"""Adapter registry keyed by file suffix."""

from __future__ import annotations

from pathlib import Path

from .adapters.base import Adapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: list[Adapter] = []

    def register(self, adapter: Adapter) -> None:
        self._adapters.append(adapter)
        self._adapters.sort(key=lambda item: max((len(sfx) for sfx in item.suffixes), default=0), reverse=True)

    def get(self, path: str | Path) -> Adapter | None:
        suffix = Path(path).suffix.lower()
        for adapter in self._adapters:
            if suffix in {item.lower() for item in adapter.suffixes}:
                return adapter
        return None

    def names(self) -> list[str]:
        return [adapter.name for adapter in self._adapters]

    def supported_extensions(self) -> list[str]:
        extensions: set[str] = set()
        for adapter in self._adapters:
            extensions.update(item.lower() for item in adapter.suffixes)
        return sorted(extensions)

    def __len__(self) -> int:
        return len(self._adapters)
