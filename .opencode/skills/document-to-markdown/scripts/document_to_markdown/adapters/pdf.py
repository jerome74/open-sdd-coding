"""PDF adapter built on Poppler (pdftotext/pdftoppm). No OCR."""

from __future__ import annotations

import re
from pathlib import Path

from ..config import Config
from ..errors import ConversionError
from .base import Adapter, ConversionResult, require_tool, run_tool
from .util import fence_for


def _page_number(path: Path) -> int:
    match = re.search(r"(\d+)(?=\.[^.]+$)", path.name)
    return int(match.group(1)) if match else 0


class PdfAdapter(Adapter):
    name = "poppler"
    suffixes = (".pdf",)

    def convert(
        self,
        source: Path,
        out_md: Path,
        media_dir: Path,
        config: Config,
    ) -> ConversionResult:
        pdftotext = require_tool(["pdftotext"])
        extraction = run_tool([pdftotext, "-layout", str(source), "-"])
        pages = extraction.stdout.split("\f")
        if pages and not pages[-1].strip():
            pages = pages[:-1]

        out_md.parent.mkdir(parents=True, exist_ok=True)
        if any(page.strip() for page in pages):
            sections = [f"# {source.stem}"]
            for number, page in enumerate(pages, start=1):
                text = page.rstrip()
                if not text.strip():
                    continue
                fence = fence_for(text)
                sections.append(f"## Pagina {number}\n\n{fence}\n{text}\n{fence}")
            out_md.write_text("\n\n".join(sections).rstrip() + "\n", encoding="utf-8")
            return ConversionResult(converted=out_md, media=None, tool="pdftotext")

        pdftoppm = require_tool(["pdftoppm"], label="pdftoppm (Poppler)")
        media_dir.mkdir(parents=True, exist_ok=True)
        prefix = media_dir / "page"
        run_tool(
            [
                pdftoppm,
                "-png",
                "-r",
                str(config.pdf_dpi),
                str(source),
                str(prefix),
            ]
        )
        images = sorted(media_dir.glob("page*.png"), key=_page_number)
        if not images:
            raise ConversionError(
                "pdftoppm non ha prodotto immagini: PDF illeggibile o non supportato",
                code="TOOL_ERROR",
            )

        sections = [f"# {source.stem}", "_PDF senza testo: pagine renderizzate come immagini._"]
        for number, image in enumerate(images, start=1):
            sections.append(f"## Pagina {number}\n\n![Pagina {number}]({media_dir.name}/{image.name})")
        out_md.write_text("\n\n".join(sections).rstrip() + "\n", encoding="utf-8")
        return ConversionResult(converted=out_md, media=media_dir, tool="pdftoppm")
