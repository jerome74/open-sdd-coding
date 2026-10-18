"""Local, stdlib-only document to Markdown conversion engine.

The package exposes a thin CLI in ``scripts/convert_documents.py`` and a
library surface used by the skill tests. It never writes outside the
configured output directory and never touches input roots.
"""

from __future__ import annotations

from .config import Config, load_config
from .errors import ConfigError, ConversionError, DocumentToMarkdownError, PathError
from .orchestrator import Orchestrator
from .registry import AdapterRegistry
from .report import Report

__all__ = [
    "AdapterRegistry",
    "Config",
    "ConfigError",
    "ConversionError",
    "DocumentToMarkdownError",
    "Orchestrator",
    "PathError",
    "Report",
    "load_config",
]
