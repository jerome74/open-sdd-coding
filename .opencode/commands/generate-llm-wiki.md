---
description: "Graph-first knowledge pipeline: detect changes in the configured source roots (raw/, docs/specs/), convert binary documents under the configured source root to Markdown under the configured derived directory and extract them as an additional Graphify root, extract the source roots into a Graphify knowledge graph, export it as an Obsidian vault, and make every generated Markdown file conformant with Google Open Knowledge Format (OKF) v0.1."
argument-hint: "'update' (default — refresh what changed), 'check' (report changes only), 'all' (full rebuild), 'okf' (re-apply OKF conversion), 'validate' (read-only gate), 'query \"<question>\"', 'report'"
---

# Knowledge pipeline — raw + spec → Graphify → Obsidian → OKF

Mode: `$1` (default `update`).

Read `knowledge-config.json` (repo root) first — it is the single source of paths, source roots,
and OKF settings. Never hard-code a path that the config already defines.

**Prerequisite:** `graphify` on the PATH (`uv tool install graphifyy`). If missing, stop and say so.

This command runs as the **primary agent** (the Conductor of the knowledge pipeline). Phase 0 runs
here; phases 1–5 are delegated to `@second-brain-keeper` via the Task tool. The OKF rules live in
the `okf-open-knowledge-format` and `wiki-to-okf` skills. Do not restate their rules here —
delegate.

## Phase 0 — Change detection and source preparation

1. **Resume check** — modes `update`, `all`, `okf`, `check` only. (`validate`, `query`, `report`
   never reach Phase 0 — skip this step for them.) Informational only: report what you find, then
   continue with the mode the user actually invoked — never switch modes on their behalf.

   - **`<pipeline_state>` exists:**
     - `last_phase_completed == "5-sealed"` → normal state, continue.
     - anything else, including `null` → a previous run was interrupted. Report the last
       completed phase and the resume command:

       | Last completed phase | What's missing | Resume command |
       |---|---|---|
       | *(none)* / `null` / `1-extract` | extraction and/or export never finished | `/generate-llm-wiki update` (or `all` for a full rebuild) |
       | `2-export`, `3-okf`, `3b-deepen`, `4-gate` | OKF, deepen, gate, or seal never finished | `/generate-llm-wiki okf` |

   - **`<pipeline_state>` absent:** do not assume "all clear" just because there is nothing to
     read — it may be a run that predates this checkpoint mechanism. Fall back to a deterministic
     check: if `<bundle_root>` already contains concept notes, grep its reserved files for the
     never-populated placeholder text:

     ```bash
     grep -l "none yet — one section per community\|No sources ingested yet" \
       "<bundle_root>/index.md" "<bundle_root>/log.md" 2>/dev/null
     ```

     If either matches while concept notes already exist, treat it as stopped at
     `2-export`/`3-okf` (same row, same resume command). If neither matches, or the bundle is
     genuinely empty, this is a normal state.

2. **Document conversion pre-pass — modes `update` and `all` only.** Skip this step entirely for
   `check`, `okf`, `validate`, `query` and `report`: those modes must never write under `<out_dir>`.

   Read `document_conversion` from `knowledge-config.json`. If the block is absent or `enabled` is
   `false`, record `conversion: disabled`, set `converted = 0`, `derived_md_count = 0`,
   `derived_indexed = true`, and continue with step 3.

   - **Guards.** `source_root` must exist, be a directory, and be listed in `immutable_roots` — it
     is read-only input. Otherwise stop with a configuration error: no conversion, no extraction,
     no seal. `stage_slug` must differ from the legacy staging slug of every entry in
     `source_roots`; a collision is a configuration error, not a silent rename.
   - `<out_dir>` = `document_conversion.out_dir`. `<derived_root>` = `<out_dir>/<root-slug>`, where
     `<root-slug>` is the skill's deterministic slug of the source-root basename (lowercase,
     non-alphanumerics → `-`; `raw` → `raw`). Both `<out_dir>` and `<derived_root>` must not equal or
     be inside any `immutable_roots` path; stop before writing otherwise.
   - **`all` only — orphan cleanup before conversion.** Delete `<out_dir>` after this guard; if any
     check fails, stop and delete nothing:
     - `<out_dir>` is strictly inside `<graph_out>` and is not `<graph_out>`;
     - `<out_dir>` does not equal and is not inside any `immutable_roots` path;
     - `<out_dir>` is not `.` and not the repository root.
     Delete with a guarded Python `shutil.rmtree` call. **Never** use `rm -rf`: `opencode.json`
     denies it.
   - **Run:**

     ```bash
     python3 <document_conversion.cli> \
       --root <source_root> \
       --out <out_dir> \
       --json
     ```

     `--json` prints one object on stdout
     (`{status, counts:{total,converted,skipped,errors}, errors:[{root,file,error}]}`); logs go to
     stderr. Never pass `--config`: the skill defaults are the contract.
   - **Exit code:**
     - `0` → conversion complete.
     - `1` → **non-blocking warning.** Keep `counts` and `errors` for the report and step 4. If
       stdout is not parseable JSON (the CLI also exits `1` on a top-level I/O error, before
       producing a report), record `conversion failed before producing a report` with the stderr
       text and continue with zero counts. Do not stop.
     - `2` → **blocking** invalid configuration, unsafe path, or active lock. Quote the stderr cause
       and stop: no extraction, no gate, no `source_watch --update`, no seal.
   - **Integrity check (read-only).** `derived_ready` is true only if all hold:
     `<derived_root>/.conversion-map.json` parses with `version: 1`; every entry with `status` in
     `{ok, skipped}` has an existing `converted` file; every non-null `media` is an existing
     directory; `<derived_root>/.conversion.lock` is absent. Do **not** compare
     `converted_sha256`: the skill would not repair a hash-only mismatch.
     `derived_md_count` = number of `.md` files under `<derived_root>`.
     `derived_indexed` = `<stage_dir>/<document_conversion.stage_slug>/.graphify_manifest.json`
     exists, or `<graph_json>` is absent (first build).
   - Report one line: `conversion: <converted> converted, <skipped> skipped, <errors> errors —
     <derived_root> (ready=<yes|no>, md=<n>, indexed=<yes|no>)`.
   - A leftover `.conversion.lock` makes the CLI exit `2`. Per the skill, delete it only when no
     conversion is running; never delete it silently.

3. Run the deterministic pre-flight:

   ```bash
   python3 scripts/source_watch.py --json
   ```

   It reports, per source root, which files were **added**, **modified**, or **deleted** since the
   last successful build. It costs nothing — no LLM call, no network. Read `changed` from the JSON,
   not the exit code: the script exits `1` when there are changes; only `2` is an error.

4. **Show the user what changed** before spending anything: one line per root with the three
   counts, then the file lists when they are short enough to be useful. Add the conversion line from
   step 2 (when it ran) and, when `errors > 0`, the list `<root>/<file>: <error>`.

5. Decide the extraction set:
   - **`all`** → every non-empty `source_root`, plus `<derived_root>` when `derived_md_count > 0`.
   - **No previous build** (`<graph_json>` absent) → every non-empty `source_root`, plus
     `<derived_root>` when `derived_md_count > 0`.
   - **`update`, source roots changed** → the changed roots; add `<derived_root>` when
     `derived_md_count > 0` and (`converted > 0` or `derived_indexed` is false).
   - **`update`, nothing changed in the source roots:**
     - `converted > 0` → the extraction set is `<derived_root>` alone (new Markdown exists; the
       bundle must not go stale);
     - `converted == 0` and `derived_md_count > 0` and `derived_indexed` is false → the extraction
       set is `<derived_root>` alone (repair an interrupted first extraction);
     - otherwise → nothing changed and the bundle already exists: say so and stop. Do not rebuild.
   - Never treat `<derived_root>` as a source root: never add it to `source_roots`, never let
     `source_watch` see it, never seal it. When the derived root enters the extraction set, pass
     `label: document_conversion.stage_label` for it.
   - When source roots report deletions under `<source_root>`, warn that `update` keeps stale
     converted Markdown until `/generate-llm-wiki all` (the skill has no prune).

6. Ask whether to add **external sources** for this run (code directories, documents). Accept a
   list of paths or `no`. External paths become additional extraction roots — they are never
   copied into `raw/`. External roots keep their legacy staging slug; `document_conversion.stage_slug`
   applies only to the converted root.

7. If every source root **and** `<derived_root>` are empty and no external source is given: report
   it and stop. Nothing to graph.

## Phases 1–5 — delegate

Invoke `@second-brain-keeper` **via the Task tool**, passing the extraction set resolved in
Phase 0, the mode, and the conversion result. Pass entries, not bare strings:

- `{path, stage_slug, origin, label}` with `origin` in `source_root | external | derived`;
- `stage_slug` is the staging directory name under `<stage_dir>`: the legacy slug for configured and
  external roots (unchanged, so existing staged graphs are reused), and
  `document_conversion.stage_slug` for the converted root;
- `origin: derived` entries are read-only input: the agent must never write, seal, prune or
  re-convert them;
- also pass `{counts, errors, derived_ready, derived_indexed}` so the agent can echo it in the final
  summary.

It runs:

1. incremental extraction of the extraction set (changed roots plus the converted root when it is
   included) in the configured `extraction_mode` (`deep` → `--mode deep`, `standard` → no flag) and
   `--backend <extraction_backend>`, then merge and re-cluster into `<graph_json>`;
2. Obsidian export into `<bundle_root>`;
3. OKF conversion of `<bundle_root>` via the `wiki-to-okf` skill;
4. **deepen** — expansion of the note bodies from their original sources;
5. the OKF conformance gate.

Steps 3 and 4 are governed by `okf_enrichment` and `deepen` in the config. Both default to `true`
and are part of every cycle — they are what keeps the notes from being bare adjacency lists.

The orchestration stays on the primary agent: a subagent cannot spawn further subagents, so
Phase 0, the user interaction and the final report belong here, not inside the agent.

**Immutable-root sweep.** After the agent returns, before sealing state, guard against stray
writes into an immutable source root:

```bash
for root in <immutable_roots>; do
  if [ -d "$root/graphify-out" ]; then
    rm -rf "$root/graphify-out"
    echo "Removed stray $root/graphify-out — immutable-root write, investigate what wrote it."
  fi
done
```

Iterate `immutable_roots` from config — never hard-code `raw`. This is a safety net, not a fix for
the root cause: if it fires, report it loudly in the final summary and say it needs investigating,
don't just clean it up in silence.

If the bundle changed this run, rebuild the search index — native, deterministic, no LLM call:

```bash
python3 .opencode/skills/wiki-semantic-search/scripts/build_index.py
```

This is what `knowledge-searcher` queries from `/gather-requirements` and `/spec-brainstorm`. Run
it every time the bundle changes materially, same trigger point as the gate itself — a stale index
answers on old content. See the `wiki-semantic-search` skill for the format and rationale (a
semantic vector index, built with the local embedding model — no API key, no query-time network).

On success, seal the new state:

```bash
python3 scripts/source_watch.py --update
```

Do this **only after** the gate passes. Sealing a failed build would hide the pending changes from
the next run.

## Modes

| Mode | Behaviour |
|---|---|
| `update` *(default)* | Phase 0 (conversion pre-pass included), then phases 1–5 on the changed roots plus the converted root when it has new Markdown. Stops early only when the source roots and the conversion produced nothing and the converted stage is already indexed. |
| `check` | **Read-only.** Phase 0 steps 1, 3 and 4 only: report what changed; inspect the existing conversion map read-only if present, but never run the conversion. No writes, no cost. |
| `all` | Full rebuild: delete `<out_dir>` (orphan cleanup), reconvert, then re-extract every non-empty root, converted root included. |
| `okf` | Skip extraction and export; re-apply phases 3, 3b and 4 on the existing bundle. |
| `validate` | **Read-only.** Run the OKF gate only and report its output verbatim. |
| `query "<question>"` | `graphify query "<question>"` against the existing graph. Generates nothing. |
| `report` | Print `GRAPH_REPORT.md` highlights, `graphify god-nodes --top 10`, and bundle counts. |

## Hard constraints

- **Never write under any path in `immutable_roots`.** In particular, never run
  `graphify extract <root>` without `--out` — it would write `<root>/graphify-out/` inside an
  immutable source root (`opencode.json` `permission.edit` denies `raw/**`, but the sweep above is
  the operational backstop).
- **Never run `graphify export wiki`** — it writes to `<graph_out>/wiki/`, which is the bundle.
  The Obsidian export (`--dir`) is the only export that produces the bundle.
- **Never delete `<stage_dir>`.** It holds the per-root incremental manifests; removing it forces
  a full paid re-extraction.
- **Phase 3 must follow every Phase 2.** The export overwrites the notes it owns, discarding all
  OKF enrichment. A bundle that was conformant before an export is not conformant after it.
- **Conversion writes only under `<out_dir>`.** `<out_dir>` is deleted only in mode `all`, only
  after the destructive-path guard.
- **The converted root is input to extraction, never a source root.** It never appears in
  `source_roots`, in `source_watch`, or in the seal.
- Everything under `<graph_out>` is **derived and regenerable**. Never defend a hand edit there;
  regenerate instead.
- Do not finish with OKF conformance errors outstanding.
- Report honestly: what changed per root, sources processed, nodes/edges/communities, bundle file
  count, gate result, whether the immutable-root sweep fired, the resume-check outcome, conversion
  counts, derived path, `derived_ready`/`derived_indexed`, the stage used, whether the derived root
  was extracted this run, and any conversion failures verbatim. When `update` sees deletions under
  `<source_root>`, say that the converted tree keeps stale Markdown until `/generate-llm-wiki all`.
