"""Pandoc adapter for DOCX/DOCM, PPTX/PPTM, ODT, HTML."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..config import Config
from ..errors import ConversionError
from .base import Adapter, ConversionResult, require_tool, run_tool

_TRACKED_SUFFIXES = {".docx", ".docm"}


class PandocAdapter(Adapter):
    name = "pandoc"
    suffixes = (".docx", ".docm", ".pptx", ".pptm", ".odt", ".html", ".htm")

    def convert(
        self,
        source: Path,
        out_md: Path,
        media_dir: Path,
        config: Config,
    ) -> ConversionResult:
        pandoc = require_tool(["pandoc"])
        if media_dir.parent != out_md.parent:
            raise ConversionError(
                "adapter pandoc: Markdown e directory media devono essere sorelle",
                code="INTERNAL",
            )
        out_md.parent.mkdir(parents=True, exist_ok=True)

        command = [pandoc, str(source), "-t", "gfm"]
        if source.suffix.lower() in _TRACKED_SUFFIXES:
            command.append("--track-changes=all")
        command.append(f"--extract-media={media_dir.name}")
        command.extend(["-o", out_md.name])

        run_tool(command, cwd=out_md.parent)
        if not out_md.is_file():
            raise ConversionError(
                f"pandoc non ha prodotto '{out_md}': documento corrotto o non leggibile",
                code="CORRUPT",
            )
        media = _normalize_media(out_md, media_dir)
        return ConversionResult(converted=out_md, media=media, tool="pandoc")


def _normalize_media(out_md: Path, media_dir: Path) -> Path | None:
    if not media_dir.is_dir():
        return None

    inner = media_dir / "media"
    if inner.is_dir():
        for item in list(inner.iterdir()):
            target = media_dir / item.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(item), str(target))
        inner.rmdir()

    files = [item for item in media_dir.rglob("*") if item.is_file()]
    if not files:
        shutil.rmtree(media_dir, ignore_errors=True)
        return None

    text = out_md.read_text(encoding="utf-8")
    replacements = {
        f"{media_dir.name}/media/": f"{media_dir.name}/",
        f"{media_dir.resolve().as_posix()}/media/": f"{media_dir.name}/",
        f"{media_dir.resolve().as_posix()}/": f"{media_dir.name}/",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    out_md.write_text(text, encoding="utf-8")
    return media_dir
