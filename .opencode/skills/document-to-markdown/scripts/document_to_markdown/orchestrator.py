"""Conversion orchestrator: discovery, adapters, publishing, map updates."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable

from .adapters.base import Adapter
from .config import Config, validate_out_dir
from .digest import file_sha256
from .discovery import discover
from .errors import ConversionError, PathError
from .guard import ensure_within, resolve_path
from .map import (
    MAP_FILENAME,
    load_map,
    make_entry,
    new_map,
    should_skip,
    write_map_atomic,
)
from .registry import AdapterRegistry
from .report import Report
from .slug import root_slug

Log = Callable[[str], None]


def _default_log(message: str) -> None:
    print(message, file=sys.stderr)


class RunLock:
    """Exclusive per-root lock; the lock file lives inside the root output."""

    def __init__(self, out_root: Path) -> None:
        self.path = out_root / ".conversion.lock"
        self._held = False

    def __enter__(self) -> "RunLock":
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError as exc:
            raise PathError(
                f"run già in corso per '{self.path.parent}': rimuovere '{self.path}' se non è attivo"
            ) from exc
        os.close(descriptor)
        self._held = True
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._held:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self._held = False


class Orchestrator:
    def __init__(
        self,
        config: Config,
        registry: AdapterRegistry,
        *,
        log: Log | None = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.log = log or _default_log

    def run(self, roots: list[Path]) -> Report:
        resolved = [resolve_path(root) for root in roots]
        for root in resolved:
            if not root.is_dir():
                raise PathError(f"root di input non trovato o non è una directory: '{root}'")
        validate_out_dir(self.config, resolved)

        slugs: list[str] = []
        taken: set[str] = set()
        for root in resolved:
            slug = root_slug(root, taken)
            taken.add(slug)
            slugs.append(slug)

        report = Report()
        for root, slug in zip(resolved, slugs):
            report.merge(self._run_root(root, slug))
        return report

    def _run_root(self, root: Path, slug: str) -> Report:
        report = Report(roots=[root])
        out_root = resolve_path(self.config.out_dir / slug)
        out_root.mkdir(parents=True, exist_ok=True)

        with RunLock(out_root):
            map_path = out_root / MAP_FILENAME
            try:
                data = load_map(map_path, root.name)
            except ConversionError as exc:
                self.log(f"attenzione: {exc}; nuova mappa")
                data = new_map(root.name)

            entries = data.setdefault("entries", {})
            for source in discover(root):
                rel = source.relative_to(root).as_posix()
                report.count("total")
                source_hash = file_sha256(source)
                previous = entries.get(rel)

                if self.config.skip_unchanged and should_skip(previous, source_hash, out_root):
                    entry = dict(previous or {})
                    entry["status"] = "skipped"
                    entries[rel] = entry
                    report.count("skipped")
                    self.log(f"skip: {rel}")
                    continue

                adapter = self.registry.get(source)
                if adapter is None:
                    message = f"UNSUPPORTED: formato non supportato: '{source.suffix.lower()}'"
                    entries[rel] = make_entry(status="error", error=message)
                    report.add_error(root, rel, message)
                    self.log(f"errore: {rel}: {message}")
                    continue

                try:
                    entry = self._convert(source, root, out_root, adapter, source_hash)
                except ConversionError as exc:
                    message = str(exc)
                    entries[rel] = make_entry(status="error", tool=adapter.name, error=message)
                    report.add_error(root, rel, message)
                    self.log(f"errore: {rel}: {message}")
                    continue
                except OSError as exc:
                    message = f"IO_ERROR: {exc}"
                    entries[rel] = make_entry(status="error", tool=adapter.name, error=message)
                    report.add_error(root, rel, message)
                    self.log(f"errore: {rel}: {message}")
                    continue
                except Exception as exc:
                    message = f"INTERNAL: {type(exc).__name__}: {exc}"
                    entries[rel] = make_entry(status="error", tool=adapter.name, error=message)
                    report.add_error(root, rel, message)
                    self.log(f"errore: {rel}: {message}")
                    continue

                entries[rel] = entry
                report.count("converted")
                self.log(f"convertito: {rel} -> {entry['converted']}")

            data["root"] = root.name
            write_map_atomic(map_path, data)
        return report

    def _convert(
        self,
        source: Path,
        root: Path,
        out_root: Path,
        adapter: Adapter,
        source_hash: str,
    ) -> dict:
        rel = source.relative_to(root)
        md_rel = rel.with_suffix(".md").as_posix()
        media_rel = rel.with_suffix(".media").as_posix()

        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=str(out_root)))
        try:
            staged_md = staging / Path(md_rel).name
            staged_media = staging / Path(media_rel).name
            ensure_within(staged_md, staging, label="output markdown")
            ensure_within(staged_media, staging, label="directory media")

            result = adapter.convert(source, staged_md, staged_media, self.config)
            ensure_within(result.converted, staging, label="output convertito")
            if result.media is not None:
                ensure_within(result.media, staging, label="media convertiti")
            if not result.converted.is_file():
                raise ConversionError(
                    f"l'adapter '{adapter.name}' non ha prodotto '{result.converted}'",
                    code="INTERNAL",
                )

            final_md = out_root / md_rel
            final_md.parent.mkdir(parents=True, exist_ok=True)
            os.replace(result.converted, final_md)

            published_media: str | None = None
            final_media = out_root / media_rel
            has_media = result.media is not None and result.media.is_dir() and any(
                item.is_file() for item in result.media.rglob("*")
            )
            if has_media:
                if final_media.exists():
                    if final_media.is_dir():
                        shutil.rmtree(final_media)
                    else:
                        final_media.unlink()
                final_media.parent.mkdir(parents=True, exist_ok=True)
                os.replace(result.media, final_media)
                published_media = media_rel
            elif final_media.exists():
                if final_media.is_dir():
                    shutil.rmtree(final_media)
                else:
                    final_media.unlink()

            return make_entry(
                status="ok",
                converted=md_rel,
                media=published_media,
                tool=result.tool,
                source_sha256=source_hash,
                converted_sha256=file_sha256(final_md),
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)
