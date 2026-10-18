"""Legacy Office adapter: converts with LibreOffice, then delegates."""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..config import Config
from ..errors import ConversionError
from .base import Adapter, ConversionResult, require_tool, run_tool
from .pandoc import PandocAdapter
from .xlsx import XlsxAdapter

_TARGETS = {
    ".doc": (".docx", "docx"),
    ".ppt": (".pptx", "pptx"),
    ".xls": (".xlsx", "xlsx"),
}


class LegacyAdapter(Adapter):
    name = "soffice"
    suffixes = (".doc", ".ppt", ".xls")

    def convert(
        self,
        source: Path,
        out_md: Path,
        media_dir: Path,
        config: Config,
    ) -> ConversionResult:
        soffice = require_tool(
            ["soffice", "libreoffice"],
            label="soffice o libreoffice (LibreOffice)",
        )
        suffix = source.suffix.lower()
        target_suffix, format_name = _TARGETS[suffix]

        with tempfile.TemporaryDirectory(prefix="document-to-markdown-legacy-") as temp_name:
            temp_dir = Path(temp_name)
            run_tool(
                [
                    soffice,
                    "--headless",
                    "--convert-to",
                    format_name,
                    "--outdir",
                    str(temp_dir),
                    str(source),
                ]
            )
            candidates = sorted(temp_dir.glob(f"*{target_suffix}"))
            if not candidates:
                raise ConversionError(
                    f"LibreOffice non ha prodotto un file '{target_suffix}' da '{source}'",
                    code="TOOL_ERROR",
                )
            converted_source = candidates[0]
            inner: Adapter
            if target_suffix in (".docx", ".pptx"):
                inner = PandocAdapter()
            else:
                inner = XlsxAdapter()
            result = inner.convert(converted_source, out_md, media_dir, config)
            return ConversionResult(
                converted=result.converted,
                media=result.media,
                tool=f"soffice+{inner.name}",
            )
