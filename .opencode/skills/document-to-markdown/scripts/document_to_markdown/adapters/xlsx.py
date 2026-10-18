"""Stdlib-only XLSX/XLSM adapter."""

from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from ..config import Config
from ..errors import ConversionError
from .base import Adapter, ConversionResult
from .util import render_table

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
M = f"{{{MAIN}}}"


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    index = 0
    for character in letters.upper():
        index = index * 26 + (ord(character) - 64)
    return max(index - 1, 0)


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    name = "xl/sharedStrings.xml"
    if name not in archive.namelist():
        return []
    root = _parse(archive, name)
    values: list[str] = []
    for item in root.findall(f"{M}si"):
        values.append("".join(node.text or "" for node in item.iter(f"{M}t")))
    return values


def _parse(archive: zipfile.ZipFile, name: str) -> ET.Element:
    try:
        return ET.fromstring(archive.read(name))
    except KeyError as exc:
        raise ConversionError(f"parte mancante nel file Excel: '{name}'", code="CORRUPT") from exc
    except ET.ParseError as exc:
        raise ConversionError(f"XML non valido in '{name}': {exc}", code="CORRUPT") from exc


def _relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    name = "xl/_rels/workbook.xml.rels"
    if name not in archive.namelist():
        return {}
    root = _parse(archive, name)
    mapping: dict[str, str] = {}
    for relationship in root.findall(f"{{{PACKAGE_REL}}}Relationship"):
        identifier = relationship.get("Id")
        target = relationship.get("Target")
        if not identifier or not target:
            continue
        if target.startswith("/"):
            resolved = target.lstrip("/")
        else:
            resolved = posixpath.normpath(posixpath.join("xl", target))
        mapping[identifier] = resolved
    return mapping


def _sheet_definitions(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    root = _parse(archive, "xl/workbook.xml")
    relationships = _relationships(archive)
    sheets: list[tuple[str, str]] = []
    container = root.find(f"{M}sheets")
    if container is None:
        return sheets
    for sheet in container.findall(f"{M}sheet"):
        name = sheet.get("name") or "Foglio"
        identifier = sheet.get(f"{{{OFFICE_REL}}}id")
        target = relationships.get(identifier or "")
        if target is None:
            raise ConversionError(f"foglio '{name}' senza relazione nel workbook", code="CORRUPT")
        sheets.append((name, target))
    return sheets


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{M}t"))
    value_node = cell.find(f"{M}v")
    value = value_node.text if value_node is not None and value_node.text is not None else ""
    if kind == "s":
        try:
            return shared[int(value)]
        except (ValueError, IndexError):
            return ""
    if kind == "b":
        return "TRUE" if value == "1" else "FALSE"
    return value


def _sheet_rows(archive: zipfile.ZipFile, target: str, shared: list[str]) -> tuple[list[list[str]], list[str]]:
    root = _parse(archive, target)
    grid: dict[int, list[str]] = {}
    data = root.find(f"{M}sheetData")
    if data is not None:
        for row in data.findall(f"{M}row"):
            try:
                row_index = int(row.get("r") or len(grid) + 1) - 1
            except ValueError:
                row_index = len(grid)
            cells: dict[int, str] = {}
            for cell in row.findall(f"{M}c"):
                value = _cell_value(cell, shared)
                if value != "":
                    cells[_column_index(cell.get("r") or "A1")] = value
            grid[row_index] = [cells[index] for index in sorted(cells)]
            if cells:
                width = max(cells) + 1
                grid[row_index] = [cells.get(index, "") for index in range(width)]

    if not grid:
        return [], []

    rows = [grid.get(index, []) for index in range(max(grid) + 1)]
    merges = [
        element.get("ref", "")
        for element in root.findall(f".//{M}mergeCell")
        if element.get("ref")
    ]
    return rows, merges


def _copy_media(archive: zipfile.ZipFile, media_dir: Path) -> list[str]:
    copied: list[str] = []
    used: set[str] = set()
    for name in sorted(archive.namelist()):
        if not name.startswith("xl/media/") or name.endswith("/"):
            continue
        base = Path(name).name
        candidate = base
        counter = 2
        while candidate.lower() in used:
            candidate = f"{Path(base).stem}-{counter}{Path(base).suffix}"
            counter += 1
        used.add(candidate.lower())
        media_dir.mkdir(parents=True, exist_ok=True)
        (media_dir / candidate).write_bytes(archive.read(name))
        copied.append(candidate)
    return copied


class XlsxAdapter(Adapter):
    name = "xlsx"
    suffixes = (".xlsx", ".xlsm")

    def convert(
        self,
        source: Path,
        out_md: Path,
        media_dir: Path,
        config: Config,
    ) -> ConversionResult:
        try:
            archive = zipfile.ZipFile(source)
        except (zipfile.BadZipFile, OSError) as exc:
            raise ConversionError(f"file Excel non valido '{source}': {exc}", code="CORRUPT") from exc

        with archive:
            names = set(archive.namelist())
            if "xl/workbook.xml" not in names:
                raise ConversionError(
                    f"file Excel non valido '{source}': manca 'xl/workbook.xml'",
                    code="CORRUPT",
                )
            shared = _shared_strings(archive)
            sheets = _sheet_definitions(archive)
            images = _copy_media(archive, media_dir)

            sections: list[str] = [f"# {source.stem}"]
            for sheet_name, target in sheets:
                rows, merges = _sheet_rows(archive, target, shared)
                sections.append(f"## {sheet_name}")
                table = render_table(rows) if rows else "_(foglio vuoto)_"
                sections.append(table)
                if merges:
                    sections.append("Celle unite: " + ", ".join(merges))
                sections.append("")

            if images:
                sections.append("## Immagini")
                for image in images:
                    sections.append(f"![{image}]({media_dir.name}/{image})")
                sections.append("")

        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")

        media = media_dir if images else None
        return ConversionResult(converted=out_md, media=media, tool="stdlib")
