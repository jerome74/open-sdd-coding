"""CSV/TSV adapter using the standard library."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from ..config import Config
from .base import Adapter, ConversionResult
from .util import render_table


def _delimiter(source: Path, sample: str) -> str:
    if source.suffix.lower() == ".tsv":
        return "\t"
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return ","
    return dialect.delimiter


class CsvAdapter(Adapter):
    name = "stdlib"
    suffixes = (".csv", ".tsv")

    def convert(
        self,
        source: Path,
        out_md: Path,
        media_dir: Path,
        config: Config,
    ) -> ConversionResult:
        text = source.read_text(encoding="utf-8-sig", errors="replace")
        delimiter = _delimiter(source, text[:4096])
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))

        out_md.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            body = "_(file vuoto)_"
        else:
            body = render_table(rows)
        out_md.write_text(f"# {source.stem}\n\n{body}\n", encoding="utf-8")
        return ConversionResult(converted=out_md, media=None, tool="stdlib")
