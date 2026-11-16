# AGENTS.md — OpenCode SDD Framework (DeepSeek)

Minimal process core, loaded on every request: read everything else only when needed.
**SDD Constitution** — `docs/specs/constitution.md`: mission, non-negotiable principles, tech stack, `## Roadmap`. Not auto-loaded: read it before any SDD work or when in doubt about *what* to build (it wins). Missing → roadmap not initialized: `/init-new-project`.

## 0. Sources
- **Capability Registry** `docs/sdd/capability-registry.md` — assets per role + model matrix; `/SDD-implement` Phase 0 fallback (path unresolved in this repo: generated fallback `.codex/capability-registry.md`).
- **Config** — `opencode.json` (provider, model, permissions), `knowledge-config.json` (knowledge pipeline paths and levers: never hard-coded).
- **Knowledge base** — before answering about project content run `python3 scripts/cag_context.py "<q>"` and **cite the notes**; no result → say so, never invent; never read `raw/` as an answer source (FR-011, BR-1).

## 1. General rules
Think before acting (undocumented requirement → stop and report) · YAGNI · surgical changes · goal-driven: state the intended outcome before editing · every piece of work traced by a `## Roadmap` item or a Micro-Spec (`/micro-spec`).

## 2. Output style — caveman mode
Chat answers **telegraphic**: no articles, filler, hedging, preambles or step narration; fragments OK; exact technical terms.
- **Exempt:** content of written files (specs, roadmap, docs, code, comments) and the `/gather-requirements` interview.
- Fixed output formats stay verbatim. Never lose meaning: paths, IDs, commands, errors, numbers, negations, conditions exact.

## 3. SDD pipeline
`/gather-requirements` → `docs/input/*.md` → `/spec-brainstorm <file>` → `docs/specs/*.spec.md` → `/init-new-project <root>` → `constitution.md` → `/SDD-implement <spec|N|-all>` ⇄ `/micro-spec <description>`. Knowledge pipeline: `/generate-llm-wiki`, `/publish-llm-wiki <name>` (prerequisite `graphify`).
- **Conductor** — `/SDD-implement` runs as primary agent and orchestrates; delegates only specialist checkpoints via Task (a subagent never spawns subagents).
- **Discovery by role** — assets under `.opencode/` bind through frontmatter, never filenames; adding an asset requires no command edit. Asset added/renamed → update the Registry.
- **`## Roadmap` = single source of state** — order and `- [ ]`/`- [x]`; check only when Plan → Produce → Validate → Publish is complete. Never state it elsewhere, never invent roadmaps.
- **One item per context** — between items: `/compact` or a new session; on resume re-read `## Roadmap`.

## 4. `raw/` immutable
Never modify, rename, move or delete anything under `raw/`: add only (new version = new file). Enforced by `opencode.json` `permissions` (`edit` deny `raw/**`).

## 5. Language
Repository artifacts — README, `docs/**`, specs, constitution, commands, agents, skills, prompts — in **English**. Conversational output and `/gather-requirements`, `/spec-brainstorm`, `/micro-spec` in the user's language (Italian by default). Otherwise follow the language of the file you are editing.

## 6. RTK and lifecycle
- Plugin `.opencode/plugins/rtk.ts` rewrites shell commands to `rtk …`; without `rtk` in PATH the command passes unchanged. Measure: `rtk gain -p`.
- `/init-new-project` may rewrite this file: it must stay a minimal core. After edits, restart the session.
