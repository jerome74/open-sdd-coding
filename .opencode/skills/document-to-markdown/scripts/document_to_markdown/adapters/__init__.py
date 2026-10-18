"""Adapter package and default registration."""

from __future__ import annotations

from ..registry import AdapterRegistry
from .base import Adapter, ConversionResult
from .csv_adapter import CsvAdapter
from .legacy import LegacyAdapter
from .pandoc import PandocAdapter
from .pdf import PdfAdapter
from .xlsx import XlsxAdapter

__all__ = [
    "Adapter",
    "ConversionResult",
    "CsvAdapter",
    "LegacyAdapter",
    "PandocAdapter",
    "PdfAdapter",
    "XlsxAdapter",
    "build_default_registry",
]


def build_default_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    for adapter in (PandocAdapter(), XlsxAdapter(), PdfAdapter(), LegacyAdapter(), CsvAdapter()):
        registry.register(adapter)
    return registry
