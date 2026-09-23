---
name: wiki-to-okf
description: >
  Use when converting an existing directory of markdown files to OKF-compliant format.
  Invoke when a wiki, knowledge base, or LLM wiki lacks YAML frontmatter, is missing
  `type` fields, or needs to be interoperable with OKF consumers. Triggers: "make this
  wiki OKF compliant", "convert my markdown folder to OKF", "add frontmatter to my docs",
  "migrate wiki to OKF", "my docs need a type field", or any request to transform an
  existing markdown directory into a valid OKF bundle.
metadata:
  author: ft.ia.br
  version: "1.0"
  date: 2026-07-19
  category: technique
---

# Converting a Wiki to OKF

Systematic workflow for migrating an existing markdown knowledge base to OKF v0.1 conformance.

**REQUIRED SKILL:** Load `okf-open-knowledge-format` before proceeding. It defines the full spec, field semantics, reserved filenames, and validation rules used throughout this skill.

---

## When to Use

- Existing `.md` directory with no or inconsistent YAML frontmatter
- Notion, Obsidian, or Confluence export needing OKF compliance
- Any LLM wiki that must be interoperable with OKF-aware agents
- User says "make this folder OKF conformant"

---

## Conversion Workflow

### Step 1 — Audit First

Scan the directory. Build an inventory before touching anything:

| Category | Condition |
|----------|-----------|
| ✅ Conformant | Has frontmatter + non-empty `type` |
| ❌ Missing frontmatter | No `---` YAML block at top |
| ❌ Missing `type` | Has frontmatter but `type` absent or empty |
| ⚠ Reserved files | `index.md` / `log.md` — check structure |
| ℹ Missing recommended | Has `type` but lacks `title` / `description` |

Report the inventory to the user. For wikis > 20 files, get confirmation before proceeding.

### Step 2 — Infer Types

For each file lacking `type`, infer from context:

1. **Directory name** — `tables/` → `Table`, `api/` → `API Endpoint`, `metrics/` → `Metric`, `playbooks/` → `Playbook`
2. **Content signals** — headings, subject matter, document tone
3. **Filename** — descriptive names often reveal type directly
4. **Ask when ambiguous** — suggest 2–3 candidates and let the user decide. Never fabricate.

### Step 3 — Add or Fix Frontmatter

For each non-conformant concept file:

```markdown
---
type: <inferred or confirmed>
title: <H1 heading or filename-derived, title-cased>
description: <first substantive sentence from body, cleaned up>
tags: [<derived from directory path + content keywords>]
timestamp: <file modification date if available, else omit>
---
```

**Rules:**
- Prepend frontmatter — **never modify existing body content**
- If partial frontmatter exists, **merge — do not replace**
- Preserve all unknown fields (OKF allows custom extensions)
- `type` is the only truly required field; add others only when reliably derivable

### Step 4 — Handle Reserved Files

| Situation | Action |
|-----------|--------|
| Non-root `index.md` with frontmatter | Remove the frontmatter — reserved files must not have it |
| Bundle-root `index.md` | May keep only `okf_version: "0.1"` frontmatter |
| `log.md` | Ensure headings use ISO 8601 (`## YYYY-MM-DD`), newest first |
| File acting as index but not named `index.md` | Add a proper `index.md` alongside; do not rename the original |

### Step 5 — Source-Specific Cleanup (when applicable)

| Source | Cleanup actions |
|--------|----------------|
| **Obsidian** | Convert `[[wikilinks]]` → `[title](./file.md)`; move inline `#tags` to frontmatter |
| **Notion export** | Strip UUID suffixes from filenames; update all internal links after rename |
| **CSV / spreadsheet** | Each row = one concept file; map columns to frontmatter fields |

Only perform these when the source is identified. Do not guess the source.

### Step 6 — Validate

Follow the validation section of `okf-open-knowledge-format`:

1. Check: `command -v okflint`
2. If available: `okflint validate ./`
3. If not: offer to install (`uv tool install okflint`), or run `scripts/validate.sh` from the OKF skill

Report in standard format:
```
✅ PASS: 14/14 concept files have valid frontmatter with type field
✅ PASS: index.md files follow reserved structure (no unexpected frontmatter)
⚠  WARNING: 3 files missing 'description' field (recommended, not required)
```

---

## Guardrails

1. **Audit before acting** — always show inventory first; never silently modify files.
2. **Never modify body content** — only add or update frontmatter.
3. **Never invent types** — suggest candidates and ask when uncertain.
4. **Preserve unknown fields** — custom extensions are valid in OKF; do not strip them.
5. **Don't rename files** — unless the user explicitly asks (Notion UUID cleanup is the only common exception).
6. **Broken links are fine** — the spec allows them; do not add or remove links unless asked.

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Adding frontmatter to `index.md` (non-root) | Remove it — reserved files must not have frontmatter |
| Using `type: ""` (empty string) | Treat as missing — `type` must be non-empty |
| Replacing existing partial frontmatter | Merge fields; preserve what's already there |
| Inferring type from filename alone | Cross-check with directory and content before deciding |
| Adding `description: ""` to pass validation | Omit empty optional fields entirely |
