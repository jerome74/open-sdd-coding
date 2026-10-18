#!/usr/bin/env python3
"""Convert local documents to Markdown.

Usage:
    python3 convert_documents.py --root <dir> [--root <dir> ...]
        [--out <dir>] [--config <file.json>] [--json]

Exit codes:
    0  every conversion completed (including incremental skips)
    1  one or more conversion errors
    2  invalid configuration or unsafe path

The CLI never writes outside ``<out_dir>/<root-slug>/`` and never contacts
the network.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from document_to_markdown.adapters import build_default_registry
from document_to_markdown.config import load_config
from document_to_markdown.errors import ConfigError, PathError
from document_to_markdown.orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="convert_documents.py",
        description="Converte documenti locali in Markdown + media sotto <out_dir>/<root-slug>/.",
    )
    parser.add_argument(
        "--root",
        action="append",
        required=True,
        metavar="DIR",
        help="directory di input (ripetibile)",
    )
    parser.add_argument(
        "--out",
        metavar="DIR",
        help="directory di output (default: graphify-out/derived)",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="file JSON di configurazione della skill",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="stampa su stdout {status, counts, errors}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_config(Path(args.config) if args.config else None, out_dir=args.out)
    except ConfigError as exc:
        print(f"errore di configurazione: {exc}", file=sys.stderr)
        return 2

    roots = [Path(item) for item in args.root]
    try:
        report = Orchestrator(config, build_default_registry()).run(roots)
    except (ConfigError, PathError) as exc:
        print(f"errore: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"errore I/O: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False))

    counts = report.counts
    print(
        "totale: {total} · convertiti: {converted} · saltati: {skipped} · errori: {errors}".format(
            **counts
        ),
        file=sys.stderr,
    )
    for error in report.errors:
        print(f"  {error['root']}/{error['file']}: {error['error']}", file=sys.stderr)

    return 0 if report.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
