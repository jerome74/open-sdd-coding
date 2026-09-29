---
description: "Graph-first knowledge pipeline: detect changes in the configured source roots (raw/, docs/specs/), extract them into a Graphify knowledge graph, export it as an Obsidian vault, and make every generated Markdown file conformant with Google Open Knowledge Format (OKF) v0.1."
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

2. Run the deterministic pre-flight:

   ```bash
   python3 scripts/source_watch.py --json
   ```

   It reports, per source root, which files were **added**, **modified**, or **deleted** since the
   last successful build. It costs nothing — no LLM call, no network.

3. **Show the user what changed** before spending anything: one line per root with the three
   counts, then the file lists when they are short enough to be useful.

4. Decide:
   - **Nothing changed** and the bundle already exists → say so and stop. Do not rebuild.
   - **Something changed** → the roots with changes are the extraction set. Roots with no changes
     are *not* re-extracted; their staged graph is reused as is.
   - **No previous build** → every non-empty root is in the extraction set.

5. Ask whether to add **external sources** for this run (code directories, documents). Accept a
   list of paths or `no`. External paths become additional extraction roots — they are never
   copied into `raw/`.

6. If every root is empty and no external source is given: report it and stop. Nothing to graph.

## Phases 1–5 — delegate

Invoke `@second-brain-keeper` **via the Task tool**, passing the extraction set resolved in
Phase 0 and the mode. It runs:

1. incremental extraction of the changed roots with `--mode <extraction_mode>` and
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
| `update` *(default)* | Phase 0, then phases 1–5 on the changed roots only. Stops early when nothing changed. |
| `check` | **Read-only.** Phase 0 step 1–2 only: report what changed and stop. No extraction, no cost. |
| `all` | Full rebuild: skip the change gate and re-extract every non-empty root from scratch. |
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
- Everything under `<graph_out>` is **derived and regenerable**. Never defend a hand edit there;
  regenerate instead.
- Do not finish with OKF conformance errors outstanding.
- Report honestly: what changed per root, sources processed, nodes/edges/communities, bundle file
  count, gate result, whether the immutable-root sweep fired, and the resume-check outcome.
