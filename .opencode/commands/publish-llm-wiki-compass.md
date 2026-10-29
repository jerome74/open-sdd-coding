---
description: "Publish the Compass-generated knowledge bundle: commit compass-out/ (the OKF/Obsidian bundle, its graph and its adapted graph) and index-compass/ on a dedicated branch and push it, respecting raw/ immutability and excluding publication.exclude (Compass cache, snapshots and store). Takes the repository/project name as argument to derive the branch and commit message."
argument-hint: "repository/project name (used to name the branch, e.g. 'heartbeat' → branch 'heartbeat_compass_wiki')"
---

# Publish Compass knowledge bundle — commit & push on a dedicated branch

Task: publish the freshly generated Compass knowledge bundle on a new branch of the **current
project repository** and push it, so a Pull Request can be opened for review.

This command runs as the **primary agent**.

`$1` = repository/project name. Used to name the branch and describe the commit. If `$1` is empty,
ask the user for it before doing anything.

Read `knowledge-config.compass.json` (repo root) first for the configured paths (`graph_out`,
`bundle_root`, `semantic_index`, `okf_validate_script`) and the publication destination
(`publication`: `remote`, `branch_pattern`, `paths`, `exclude`). Never read `knowledge-config.json`
implicitly and never hard-code the remote, branch, paths or exclusions.

## Preconditions (verify first — stop if unmet)

1. The OKF conformance gate passes on the bundle: run `/generate-llm-wiki-compass validate` (or
   directly `bash <okf_validate_script> <bundle_root>`). It MUST exit **0**. Never publish with
   conformance errors.
2. The semantic index exists (`index-compass/index.json`, or the compressed layout) and was
   regenerated on the latest bundle. If it is missing or stale:
   ```bash
   python3 .opencode/skills/wiki-semantic-search/scripts/build_index.py \
     --config knowledge-config.compass.json
   ```
3. `compass_graph_check.py` exits `0` on the adapted graph. A published bundle backed by a graph
   with broken endpoints or missing labels is not reviewable.
4. The configured `publication.remote` exists (`git remote -v`). If not, tell the user to add it and
   stop — do not invent a URL.
5. **Overwrite gate (BR-5).** Run the read-only gate with this pipeline's config:
   ```bash
   python3 scripts/publish_gate.py <name> --config knowledge-config.compass.json
   ```
   - exit `0` / `decision: proceed` → no index in the destination; continue.
   - exit `1` / `decision: confirm-required` → an index already exists there: **ask the operator for
     explicit confirmation before overwriting**. Without it, do not publish the index — abort (or,
     if you continue at all, stage `compass-out/` only, never `index-compass/`).
   - exit `2` → report the error and stop.

## Steps

1. **Branch name.** Read `publication.branch_pattern` from `knowledge-config.compass.json` and
   substitute `{name}` with `$1` (pattern `{name}_compass_wiki` + `heartbeat` →
   `heartbeat_compass_wiki`). This is the same branch the overwrite gate inspected. Show it to the
   user and let them override. It is deliberately different from the graphify branch: the two
   bundles never land on the same branch.
2. **Create the branch:**
   ```bash
   git checkout -b <branch>
   ```
3. **Stage ONLY the generated artifacts** — the paths listed in `publication.paths`
   (`compass-out/`, `index-compass/`):
   ```bash
   git add -A compass-out/ index-compass/
   ```
   Use `-A` so files removed in the new generation (stale snapshots, stale index parts) are deleted
   in the commit too. The bundle and the index go in a **single commit**.
4. **Remove excluded paths from the index** — for every entry of `publication.exclude`
   (`compass-out/cache`, `compass-out/snapshots`, `compass-out/store`):
   ```bash
   git rm -r --cached --ignore-unmatch -- <exclude path>
   ```
   `--cached` keeps the working tree (the next run reuses Compass's incremental cache);
   `--ignore-unmatch` is a no-op when the path was never tracked. Report staged deletions.
5. **Safety check — no source files and no excluded paths:** run `git status` and confirm **NO file
   under `raw/` is staged**. `raw/` is immutable. If anything under `raw/` is staged, unstage it
   (`git restore --staged raw/`) and stop to investigate. Then, for every entry of
   `publication.exclude`:
   ```bash
   git ls-files -- <exclude path>                       # must print nothing
   git diff --cached --name-status -- <exclude path>    # only lines starting with D
   ```
   `A`/`M` rows (or non-empty `git ls-files`) mean the exclusion failed: **stop, do not commit**.
   `D` rows are the intended removal of previously tracked derived paths; report them.
6. **Commit** using the convention `wiki(<action>): <subject> — <what and why>`:
   ```bash
   git commit -m "wiki(ingest): <name> — compass knowledge bundle + semantic index"
   ```
7. **Push** and set the upstream, using the configured `publication.remote` (`<remote>`):
   ```bash
   git push -u <remote> <branch>
   ```
8. **Report** the branch name and remind the user to open the Pull Request on their host.

## Rules

- **Never stage or commit anything under `raw/`** — it is the immutable source layer.
- **Never push when the OKF gate reports errors** — fix them first
  (`/generate-llm-wiki-compass okf`, then `validate`).
- **Never push when `compass_graph_check.py` fails** — the consumers would get a broken graph.
- **BR-5 (overwrite confirmation):** when `publish_gate.py` reports `confirm-required`, get explicit
  operator confirmation before staging `index-compass/`.
- Stage only the configured `publication.paths` (`compass-out/`, `index-compass/`) — nothing else.
- **Never stage or commit anything under `publication.exclude`**: Compass cache, snapshots and store
  are regenerable, not published artifacts.
- Never publish on the graphify branch pattern (`{name}_llm_wiki`): keep the two bundles separate.
- Commit message MUST follow `wiki(<action>): <subject> — <what and why>`.
- This is a git write operation on a new branch: never commit to `main` directly, and confirm the
  branch name with the user before pushing.
