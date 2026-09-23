---
description: "Publish the generated knowledge bundle: commit graphify-out/ (the OKF/Obsidian bundle and its persistent graph) and index/ on a dedicated branch and push it, respecting raw/ immutability. Takes the repository/project name as argument to derive the branch and commit message."
argument-hint: "repository/project name (used to name the branch, e.g. 'heartbeat' → branch 'heartbeat_llm_wiki')"
---

# Publish knowledge bundle — commit & push on a dedicated branch

Task: publish the freshly generated knowledge bundle on a new branch of the **current project
repository** and push it, so a Pull Request can be opened for review.

This command runs as the **primary agent**.

`$1` = repository/project name. Used to name the branch and describe the commit. If `$1` is empty,
ask the user for it before doing anything.

Read `knowledge-config.json` (repo root) first for the configured paths (`graph_out`,
`bundle_root`, `semantic_index`, `okf_validate_script`).

## Preconditions (verify first — stop if unmet)

1. The OKF conformance gate passes on the bundle: run `/generate-llm-wiki validate` (or directly
   `bash .opencode/skills/okf-open-knowledge-format/scripts/validate.sh graphify-out/wiki`). It
   MUST exit **0**. Never publish with conformance errors.
2. `index/index.json` exists and was regenerated on the latest bundle. If it is missing or stale,
   run `python3 .opencode/skills/wiki-semantic-search/scripts/build_index.py` first (see the
   `wiki-semantic-search` skill), then continue.
3. A git remote named `origin` exists (`git remote -v`). If not, tell the user to add it and stop —
   do not invent a URL.

## Steps

1. **Branch name.** Derive `<branch>` = `<name>_llm_wiki` from `$1` (e.g. `heartbeat` →
   `heartbeat_llm_wiki`). Show it to the user and let them override.
2. **Create the branch:**
   ```bash
   git checkout -b <branch>
   ```
3. **Stage ONLY the generated artifacts** — the knowledge bundle (graph + OKF/Obsidian vault) and
   the semantic index:
   ```bash
   git add graphify-out/ index/
   ```
4. **Safety check — no source files:** run `git status` and confirm **NO file under `raw/` is
   staged**. `raw/` is immutable. If anything under `raw/` is staged, unstage it
   (`git restore --staged raw/`) and stop to investigate — never force it through.
5. **Commit** using the convention `wiki(<action>): <subject> — <what and why>`, with `<action>` one
   of `create | update | merge | ingest | audit`. For a full ingestion publish:
   ```bash
   git commit -m "wiki(ingest): <name> — knowledge graph bundle + semantic index"
   ```
   Replace `<name>` with `$1`.
6. **Push** and set the upstream:
   ```bash
   git push -u origin <branch>
   ```
7. **Report** the branch name and remind the user to open the Pull Request on their host.

## Rules

- **Never stage or commit anything under `raw/`** — it is the immutable source layer
  (`opencode.json` `permission.edit` denies `raw/**`; this is the git-level backstop).
- **Never push when the OKF gate reports errors** — fix them first (`/generate-llm-wiki okf`, then
  `validate`).
- Stage only `graphify-out/` and `index/` — nothing else, unless the user explicitly asks.
- Commit message MUST follow `wiki(<action>): <subject> — <what and why>`.
- This is a git write operation on a new branch: never commit to `main` directly, and confirm the
  branch name with the user before pushing. `git push` prompts for approval (`opencode.json`
  `permission.bash` → `"git push": "ask"`).
