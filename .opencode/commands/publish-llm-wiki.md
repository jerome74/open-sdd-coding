---
description: "Publish the generated knowledge bundle: commit graphify-out/ (the OKF/Obsidian bundle and its persistent graph) and index/ on a dedicated branch and push it, respecting raw/ immutability and excluding publication.exclude (derived extraction input). Takes the repository/project name as argument to derive the branch and commit message."
argument-hint: "repository/project name (used to name the branch, e.g. 'heartbeat' → branch 'heartbeat_llm_wiki')"
---

# Publish knowledge bundle — commit & push on a dedicated branch

Task: publish the freshly generated knowledge bundle on a new branch of the **current project
repository** and push it, so a Pull Request can be opened for review.

This command runs as the **primary agent**.

`$1` = repository/project name. Used to name the branch and describe the commit. If `$1` is empty,
ask the user for it before doing anything.

Read `knowledge-config.json` (repo root) first for the configured paths (`graph_out`,
`bundle_root`, `semantic_index`, `okf_validate_script`) and the publication destination
(`publication`: `remote`, `branch_pattern`, `paths`, `exclude`). Never hard-code the remote, branch,
paths or exclusions.

## Preconditions (verify first — stop if unmet)

1. The OKF conformance gate passes on the bundle: run `/generate-llm-wiki validate` (or directly
   `bash .opencode/skills/okf-open-knowledge-format/scripts/validate.sh graphify-out/wiki`). It
   MUST exit **0**. Never publish with conformance errors.
2. The semantic index exists (`index/index.json`, or `index/manifest.json` in the compressed
   layout) and was regenerated on the latest bundle. If it is missing or stale,
   run `python3 .opencode/skills/wiki-semantic-search/scripts/build_index.py` first (see the
   `wiki-semantic-search` skill), then continue.
3. The configured `publication.remote` exists (`git remote -v`). If not, tell the user to add it and
   stop — do not invent a URL.
4. **Overwrite gate (BR-5).** Run the read-only gate:
   ```bash
   python3 scripts/publish_gate.py <name>
   ```
   - exit `0` / `decision: proceed` → no index in the destination; continue.
   - exit `1` / `decision: confirm-required` → an index already exists there: **ask the operator for
     explicit confirmation before overwriting**. Without it, **do not publish the index** — abort
     (or, if you continue at all, stage `graphify-out/` only, never `index/`).
   - exit `2` → report the error and stop.

## Steps

1. **Branch name.** Read `publication.branch_pattern` from `knowledge-config.json` and substitute
   `{name}` with `$1` (e.g. pattern `{name}_llm_wiki` + `heartbeat` → `heartbeat_llm_wiki`). This is
   the same branch the overwrite gate inspected. Show it to the user and let them override.
2. **Create the branch:**
   ```bash
   git checkout -b <branch>
   ```
3. **Stage ONLY the generated artifacts** — the paths listed in `publication.paths` (default
   `graphify-out/ index/`). Use `-A` so files removed in the new generation (e.g. stale
   `index/parts/*` from a previous compressed index) are deleted in the commit too:
   ```bash
   git add -A graphify-out/ index/   # substitute the configured publication.paths
   ```
   The wiki and the index go in a **single commit** — the index is never published partially.
4. **Remove excluded paths from the index** — for every entry of `publication.exclude` (default
   `graphify-out/derived`):
   ```bash
   git rm -r --cached --ignore-unmatch -- <exclude path>
   ```
   `--cached` keeps the working tree (the next `/generate-llm-wiki` run reuses the converted tree);
   `--ignore-unmatch` is a no-op when the path was never tracked. When the path *was* tracked on the
   base branch this stages its deletion, so the published branch drops it — intended. Report the
   number of staged deletions.
5. **Safety check — no source files and no excluded paths:** run `git status` and confirm **NO file
   under `raw/` is staged**. `raw/` is immutable. If anything under `raw/` is staged, unstage it
   (`git restore --staged raw/`) and stop to investigate — never force it through. Then, for every
   entry of `publication.exclude`:
   ```bash
   git ls-files -- <exclude path>                       # must print nothing
   git diff --cached --name-status -- <exclude path>    # only lines starting with D
   ```
   `A`/`M` rows (or non-empty `git ls-files`) mean the exclusion failed: **stop, do not commit**.
   `D` rows are the intended removal of previously tracked derived paths; report them.
6. **Commit** using the convention `wiki(<action>): <subject> — <what and why>`, with `<action>` one
   of `create | update | merge | ingest | audit`. For a full ingestion publish:
   ```bash
   git commit -m "wiki(ingest): <name> — knowledge graph bundle + semantic index"
   ```
   Replace `<name>` with `$1`.
7. **Push** and set the upstream, using the configured `publication.remote` (`<remote>`):
   ```bash
   git push -u <remote> <branch>
   ```
8. **Report** the branch name and remind the user to open the Pull Request on their host.

## Rules

- **Never stage or commit anything under `raw/`** — it is the immutable source layer
  (`opencode.json` `permission.edit` denies `raw/**`; this is the git-level backstop).
- **Never push when the OKF gate reports errors** — fix them first (`/generate-llm-wiki okf`, then
  `validate`).
- **BR-5 (overwrite confirmation):** when `scripts/publish_gate.py` reports `confirm-required`, get
  explicit operator confirmation before staging `index/`; without it, do not publish the index.
- Stage only the configured `publication.paths` (default `graphify-out/` and `index/`) — nothing
  else, unless the user explicitly asks.
- **Never stage or commit anything under `publication.exclude`** (default `graphify-out/derived`):
  it is regenerable extraction input, not a published artifact. After staging, remove it from the
  index with `git rm -r --cached --ignore-unmatch`.
- Commit message MUST follow `wiki(<action>): <subject> — <what and why>`.
- This is a git write operation on a new branch: never commit to `main` directly, and confirm the
  branch name with the user before pushing. `git push` prompts for approval (`opencode.json`
  `permission.bash` → `"git push": "ask"`).
