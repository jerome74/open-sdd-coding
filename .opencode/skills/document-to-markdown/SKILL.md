---
name: document-to-markdown
description: Convert local Word, PowerPoint, Excel, and PDF documents to Markdown plus extracted media. Use when asked to convert documents to Markdown, extract text/tables from .docx/.pptx/.xlsx/.pdf, prepare binary documents for reading or search, or handle legacy .doc/.ppt/.xls files. Local-only engine; no network, no LLM, no Python dependencies.
---

# document-to-markdown

Convert binary documents into Markdown files and extracted media under a single
derived output directory. The skill is a reading aid: it reads the input root,
writes only under `<out_dir>/<root-slug>/`, and never modifies the source tree.

## When to use

Use it when the user asks to:

- convert Word, PowerPoint, Excel, or PDF files to Markdown;
- extract text, tables, or images from Office/PDF documents;
- make folders of binary documents readable or searchable;
- handle legacy Office files (`.doc`, `.ppt`, `.xls`).

Do not use it for OCR, cloud/LLM conversion, or files that are already textual
(`.md`, `.txt`, images).

## Prerequisites

| Tool | Required for | Check |
|---|---|---|
| Python 3.10+ | always | `python3 --version` |
| `pandoc` | `.docx/.docm/.pptx/.pptm/.odt/.html` | `pandoc --version` |
| `pdftotext`, `pdftoppm` | `.pdf` | `pdftotext -v` |
| `soffice` or `libreoffice` | `.doc/.ppt/.xls` | `soffice --version` |

Nothing is installed automatically. If a required tool is missing, the affected
document becomes `status: "error"` with code `TOOL_MISSING` and the run exits `1`.

## Command

Run from the repository root (or use the absolute path to the script):

```bash
python3 .opencode/skills/document-to-markdown/scripts/convert_documents.py \
  --root raw \
  --out graphify-out/derived \
  --json
```

Multiple roots are allowed:

```bash
python3 .opencode/skills/document-to-markdown/scripts/convert_documents.py \
  --root docs/input --root raw --out /tmp/derived
```

### Options

| Option | Meaning |
|---|---|
| `--root DIR` | Input directory. Repeatable. Required. |
| `--out DIR` | Output directory. Default `graphify-out/derived` (relative to the current directory). |
| `--config FILE` | Optional skill-local JSON configuration. |
| `--json` | Print `{status, counts, errors}` on stdout. Logs stay on stderr. |

`--prune` is intentionally not exposed: orphan cleanup is not implemented yet.
A config with `"prune": true` is rejected with exit `2`.

### Configuration file

```json
{
  "out_dir": "graphify-out/derived",
  "pdf_dpi": 120,
  "skip_unchanged": true,
  "prune": false
}
```

All keys are optional. The file is read-only for the skill and is never created
by it. `out_dir` set on the command line wins over the file.

## Formats

| Format | Extension | Tool | Notes |
|---|---|---|---|
| Word | `.docx`, `.docm` | pandoc | `--track-changes=all`; GFM may flatten some revisions |
| PowerPoint | `.pptx`, `.pptm` | pandoc | one Markdown per deck; images extracted |
| Excel | `.xlsx`, `.xlsm` | stdlib | one Markdown per workbook; one section per sheet |
| PDF | `.pdf` | Poppler | text pages via `pdftotext -layout`; scanned pages rendered at `pdf_dpi` |
| Legacy Office | `.doc`, `.ppt`, `.xls` | LibreOffice + adapter | explicit error if LibreOffice is missing |
| OpenDocument | `.odt` | pandoc | optional format |
| HTML | `.html`, `.htm` | pandoc | optional format |
| CSV/TSV | `.csv`, `.tsv` | stdlib | first row is the table header |

Excel rendering covers shared strings, inline strings, booleans, merged cells,
sheet order, and workbook images. Numeric dates stay as Excel serial numbers;
cached formula values are shown only when the workbook contains them.

## Output layout

```text
<out_dir>/
└── <root-slug>/
    ├── .conversion-map.json
    ├── report.md
    ├── report.media/
    │   └── image1.png
    └── nested/
        └── sheet.md
```

- `<root-slug>` is the root directory name in kebab-case. Collisions between
  roots with the same name become `name`, `name-2`, `name-3`, deterministically.
- The input tree is mirrored: `a/b/doc.docx` becomes `a/b/doc.md` and, when
  present, `a/b/doc.media/`.
- Media links inside Markdown are relative to the Markdown file.
- The output directory must not equal or live inside an input root. Violations
  exit `2` before any write.

## Conversion map

`<out_dir>/<root-slug>/.conversion-map.json` is written atomically:

```json
{
  "version": 1,
  "root": "raw",
  "generated_at": "2026-10-18T10:00:00+00:00",
  "entries": {
    "doc.docx": {
      "status": "ok",
      "converted": "doc.md",
      "media": "doc.media",
      "tool": "pandoc",
      "source_sha256": "…",
      "converted_sha256": "…",
      "error": null
    },
    "bad.docx": {
      "status": "error",
      "converted": null,
      "media": null,
      "tool": "pandoc",
      "source_sha256": null,
      "converted_sha256": null,
      "error": "CORRUPT: pandoc non ha prodotto …"
    }
  }
}
```

`converted` and `media` are relative to `<out_dir>/<root-slug>/`. `media` is a
directory or `null`. `source_sha256` is `null` only for error entries.

## Incremental runs

A document is skipped when all of these hold:

1. the map has a previous `ok`/`skipped` entry;
2. `source_sha256` is unchanged;
3. the Markdown file exists;
4. the media directory exists (or the entry has no media).

There is no `--force`. To reconvert, change the source or set
`"skip_unchanged": false` in the config. A skipped entry is stored with
`status: "skipped"` and keeps its previous hashes.

## Exit codes and errors

| Code | Meaning |
|---|---|
| `0` | All documents converted or skipped. |
| `1` | At least one document failed (`errors` is non-empty). |
| `2` | Invalid configuration or unsafe path (missing root, output inside input, active lock). |

Per-document error prefixes stored in the map and printed on stderr:

| Prefix | Cause |
|---|---|
| `TOOL_MISSING` | Required external tool not on `PATH`. |
| `TOOL_ERROR` | Tool ran but failed (corrupt file, unsupported variant). |
| `TOOL_TIMEOUT` | Tool exceeded the 180-second timeout. |
| `CORRUPT` | Document structure is invalid. |
| `UNSUPPORTED` | No adapter registered for the extension. |
| `MAP` | Existing conversion map is invalid; the run starts from a new map. |
| `IO_ERROR` / `INTERNAL` | Unexpected filesystem or engine failure. |

Messages are in Italian and include the exact path and cause. Logs go to
stderr; `--json` payload goes to stdout.

## Safety guarantees

- No network access and no LLM calls.
- No Python dependencies outside the standard library.
- Invalid paths (`..`, symlinks escaping the root, absolute paths) are rejected.
- Symlinks that escape the input root are ignored during discovery.
- Outputs are confined to `<out_dir>/<root-slug>/`; source roots are read-only.
- Markdown and map writes are atomic (`os.replace` after a temporary file).
- One run per root at a time via `<out_dir>/<root-slug>/.conversion.lock`.
  If no run is active and a stale lock remains, delete that file.

## Limits

- No OCR: scanned PDFs become page images with links.
- DOCX tracked changes are requested from Pandoc but GFM output may not preserve
  every revision; do not treat the result as legally faithful.
- Excel dates remain serial numbers; number formats are not rendered; formulas
  are not calculated.
- LibreOffice may change legacy document layout and is slower than native tools.
- Hidden files, Office lock files (`~$*`), and `.tmp/.part/.lock` files are
  ignored.
- `.md`, `.txt`, and image files are out of scope.

