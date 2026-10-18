"""Typed errors for the document-to-markdown engine.

Exit code mapping is owned by the CLI: ``ConfigError`` and ``PathError``
produce exit 2, while ``ConversionError`` produces exit 1.
"""

from __future__ import annotations


class DocumentToMarkdownError(Exception):
    """Base class for every engine error."""


class ConfigError(DocumentToMarkdownError):
    """Invalid configuration: unknown key, bad type, or unsupported lever."""


class PathError(DocumentToMarkdownError):
    """Unsafe or invalid path: missing root, traversal, or output inside input."""


class ConversionError(DocumentToMarkdownError):
    """A document could not be converted.

    ``code`` is a stable prefix stored in the conversion map, for example
    ``TOOL_MISSING`` or ``CORRUPT``.
    """

    def __init__(self, message: str, code: str = "CONVERSION") -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
