---
description: "Compass-first knowledge pipeline: detect changes in the configured source roots (raw/, docs/specs/), build them into a Compass structural knowledge graph under compass-out/, export it as an Obsidian vault, and make every generated Markdown file conformant with Google Open Knowledge Format (OKF) v0.1. Parallel to /generate-llm-wiki (graphify): separate assets, same OKF contract and gate, one active knowledge base at a time."
argument-hint: "'update' (default — refresh what changed), 'check' (report changes only), 'all' (full rebuild), 'okf' (re-apply OKF conversion), 'validate' (read-only gate), 'query \"<question>\"', 'report'"
---

# Knowledge pipeline — raw + spec → Compass → Obsidian → OKF

Mode: `$1` (default `update`).

Read `knowledge-config.compass.json` (repo root) first — it is the single source of paths, source
roots, Compass settings and OKF settings for this pipeline. Never read `knowledge-config.json`
implicitly: that file belongs to the graphify pipeline. Never hard-code a path the config defines.

**Prerequisite:** `compass` on the PATH, version at least `compass_min_version`. If it is missing or
older, **stop** and ask the user to install it from the official release assets. Never install it
automatically, and never run `compass install` in this repository: it writes `AGENTS.md`, `.agents/`
and editor rule files.

This command runs as the **primary agent**. Phase 0 runs here; phases 1–5 are delegated to
`@compass-keeper` via the Task tool. The OKF rules live in the `okf-open-knowledge-format` and
`wiki-to-okf` skills — do not restate them.

## Phase 0 — Preflight, change detection and source preparation

1. **Preflight — every mode, read-only.**

   ```bash
   command -v compass
   compass --version
   python3 scripts/compass_config_gen.py --check
   ```

   - Missing binary → stop: instruct the user to install `compass-v<compass_min_version>` (release
     asset for their platform) and retry. No automatic install.
   - Installed version lower than `compass_min_version` → stop with the measured version.
   - `compass_config_gen.py --check` non-zero → run `python3 scripts/compass_config_gen.py` once,
     report it, and continue. `.compass/config.toml` is generated from the config, never hand-edited.
   - **Corpus guard:** if every entry of `source_roots` contains no eligible file (only ignored
     files such as `.gitkeep`), stop with `corpus empty: add sources under <roots>` — `compass init`
     would fail with exit 2 and there is nothing to build.
   - For `validate`, `query` and `report`, skip steps 2–5 and go straight to the matching behaviour
     in the Modes table.

2. **Resume check** — modes `update`, `all`, `okf`, `check` only. Informational only: report what you
   find, then continue with the mode the user invoked — never switch modes on their behalf.

   - `<pipeline_state>` exists:
     - `last_phase_completed == "5-sealed"` → normal state, continue.
     - anything else → a previous run was interrupted. Report the last completed phase and the
       resume command:

       | Last completed phase | What's missing | Resume command |
       |---|---|---|
       | *(none)* / `null` / `1-extract` | extraction and/or export never finished | `/generate-llm-wiki-compass update` (or `all` for a full rebuild) |
       | `2-export`, `3-okf`, `3b-deepen`, `4-gate` | OKF, deepen, gate, or seal never finished | `/generate-llm-wiki-compass okf` |

   - `<pipeline_state>` absent: fall back to a deterministic check. If `<bundle_root>` already
     contains concept notes, grep its reserved files for the never-populated placeholder text:

     ```bash
     grep -l "none yet — one section per community\|No sources ingested yet" \
       "<bundle_root>/index.md" "<bundle_root>/log.md" 2>/dev/null
     ```

     If either matches while concept notes exist, treat it as stopped at `2-export`/`3-okf`. If
     neither matches, or the bundle is empty, this is a normal state.

3. **No document conversion pre-pass.** Compass parses PDF/Office documents natively into structural
   nodes (OCR is opt-in and downloads models — never enable it implicitly). Record
   `conversion: native`, `derived = 0` and continue. Do not run the `document-to-markdown` skill for
   this pipeline.

4. Run the deterministic pre-flight:

   ```bash
   python3 scripts/source_watch.py --json --config knowledge-config.compass.json
   ```

   Read `changed` from the JSON, not the exit code: the script exits `1` when there are changes;
   only `2` is an error. The manifest lives under `compass-out/` and never collides with the
   graphify manifest.

5. **Show the user what changed** before spending anything: one line per root with added, modified
   and deleted counts, then the file lists when they are short enough to be useful.

6. **Decide whether to build:**
   - `all` → build. Pass `force: true` to the agent so Compass rebuilds instead of reusing cache.
   - `<compass_graph_json>` absent → build.
   - `update` with `changed == true` → build.
   - `update` with `changed == false` and the bundle already exists → say so and stop. Do not
     rebuild.
   - **External sources** (code directories outside the configured roots) are **not supported** in
     this version: Compass builds a single project scope from `.compass/config.toml`. Say so
     explicitly if the user asks for them; never inject them into `raw/`.

7. If every configured root is empty: report it and stop. Nothing to graph.

## Phases 1–5 — delegate

Invoke `@compass-keeper` **via the Task tool**, passing:

- `{mode, force, counts}` where `counts` is the per-root change report from step 5;
- the fact that the raw graph is `compass_graph_json` and the adapted graph is `graph_json`.

The agent runs:

1. Compass build (incremental, or forced for `all`), then the adapter and the contract check;
2. Obsidian export into `<bundle_root>`;
3. OKF conversion via the `wiki-to-okf` skill;
4. deepen, expansion of note bodies from their sources;
5. the OKF conformance gate;
6. the seal.

The orchestration stays on the primary agent: a subagent cannot spawn further subagents, so
Phase 0, user interaction and the final report belong here.

**Immutable-root sweep.** After the agent returns, before sealing state:

```bash
for root in <immutable_roots>; do
  for stray in compass-out .compass; do
    if [ -e "$root/$stray" ]; then
      rm -rf "$root/$stray"
      echo "Removed stray $root/$stray — immutable-root write, investigate what wrote it."
    fi
  done
done
```

Iterate `immutable_roots` from config — never hard-code `raw`. Report loudly if it fires.

If the bundle changed this run, rebuild the search index — deterministic, no LLM call:

```bash
python3 .opencode/skills/wiki-semantic-search/scripts/build_index.py \
  --config knowledge-config.compass.json
```

On success, seal the new state (only after the gate passes):

```bash
python3 scripts/source_watch.py --update --config knowledge-config.compass.json
```

**Then point the active knowledge base at this pipeline** — only after the gate passed and the seal
succeeded:

```bash
python3 scripts/kb_active.py set compass
```

This rewrites only `graph_json`, `bundle_root` and `semantic_index` in `knowledge-config.json`, so
the consumers read the Compass knowledge base. A pointer failure is a warning, not a build failure:
the bundle stays valid and the previous active KB stays selected.

## Modes

| Mode | Behaviour |
|---|---|
| `update` *(default)* | Phase 0, then phases 1–5 when something changed. Stops early when the source roots and the bundle are already in sync. |
| `check` | **Read-only.** Phase 0 steps 2 and 4–5 only: report what changed. No writes, no cost. |
| `all` | Full rebuild: Compass is forced to rebuild, then phases 1–5. Never delete `compass-out/`, its cache or its snapshots. |
| `okf` | Skip build and export; re-apply phases 3, 3b and 4 on the existing bundle. |
| `validate` | **Read-only.** Run the OKF gate only and report its output verbatim. |
| `query "<question>"` | `compass query "<question>"` against the existing graph. Generates nothing. |
| `report` | Print `GRAPH_REPORT.md` highlights, `compass community` summary, and bundle counts. |

## Hard constraints

- **Never write under any path in `immutable_roots`.** Compass runs from the repository root and
  writes `compass-out/`; the sweep above is the operational backstop.
- **Never run `compass install`** (or `hook`, `provider add`, `add`, `clone`, `models install`) in
  this repository: they write `AGENTS.md`, `.agents/`, `.cursor/`, `.trae/`.
- **Never run `compass export wiki`** — it has no `--dir` flag and writes to `compass-out/wiki/`.
  `compass export obsidian --dir <bundle_root>` is the only export that produces the bundle.
- **Never delete `compass-out/`, `compass-out/cache/` or `compass-out/snapshots/`** — they are the
  incremental state.
- **Never run `compass init` on this repository** while the corpus is empty: it exits 2. The config
  is generated by `scripts/compass_config_gen.py`.
- **Phase 3 must follow every Phase 2.** The export overwrites the notes it owns, discarding the OKF
  enrichment. A bundle that was conformant before an export is not conformant after it.
- **Never point the active KB before gate and seal.** `kb_active.py` must run last, and only on a
  successful cycle.
- **One active KB only.** Never make both `graphify-out` and `compass-out` implicitly readable: the
  inactive one is reachable only with `--config`.
- Everything under `compass-out/` is derived and regenerable. Never defend a hand edit there.
- Report honestly: what changed per root, whether the build was forced, raw and adapted graph
  counts, check result, bundle file count, gate result, deepen verification, seal outcome, active KB
  after the switch, and any sweep that fired. If the gate failed, say so and do not seal.
