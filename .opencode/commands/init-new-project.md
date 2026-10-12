---
description: "Initialize a new project: generate constitution.md and AGENTS.md from functional specs"
argument-hint: "Path to the project root folder to initialize"
---

# Project Initialization — Spec-Driven Development

You are a project architect. Your task is to bootstrap the foundational project files from the functional specifications. This command runs as the **primary agent**.

## Input

Project root: `$1` (defaults to current workspace root if not specified)

## Prerequisites

Before proceeding, verify:
1. Functional specs exist in `docs/specs/` — if the folder is empty or missing, **STOP immediately** and ask the user to run `/spec-brainstorm` first to generate the spec files. Do NOT proceed without specs.
2. Template exists at [template.constitution.md](../../docs/templates/template.constitution.md) (`docs/templates/template.constitution.md`)

## Process

### Step 1 — Read Context

- Read ALL spec files in `docs/specs/` to understand the project scope, features, actors, and tech stack.
- Read the template at `docs/templates/template.constitution.md`.

### Step 2 — Generate `constitution.md`

Create `constitution.md` in the `docs/specs/` folder, following the template structure:

- **Mission**: Synthesize the North Star objective from all specs. Describe the problem context, current pain points, and list non-negotiable principles.
- **Tech Stack**: Extract from specs or infer from existing project structure. Pin specific versions where the specs state them. Define mandatory architectural patterns and constraints.
- **Roadmap**: Generate a checklist of features derived from each spec file in `docs/specs/`, linking back to the spec filenames.

Language: Italian (matching specs).

### Step 3 — Generate `AGENTS.md`

Create `AGENTS.md` at the **project root** — it is the primary instructions file OpenCode auto-loads for this project. **Do not create or edit `CLAUDE.md`.** Contextualize `AGENTS.md` for the project:

- Reference `constitution.md` as the **Costituzione SDD** (Spec-Driven Development) del progetto — the authoritative source for project mission, principles, tech stack, and roadmap.
- Include a General Agent Guidelines section with rules for: think before coding, simplicity first, surgical changes, goal-driven execution.
- Include project-specific conventions derived from the tech stack.
- Preserve any existing framework rules already in `AGENTS.md` (sources, Conductor rule,
  discovery-by-role, roadmap-as-truth, one-item-per-context, caveman output style, `raw/`
  immutability, language convention). Merge — do not overwrite them.
- `AGENTS.md` is loaded on **every request**: keep it a minimal core (target ≤ 4K characters). Link
  to `constitution.md` and `docs/sdd/capability-registry.md` instead of duplicating them; never move
  the Capability Registry back into `AGENTS.md`, and never add `constitution.md` to
  `opencode.json` `instructions`.

> If OpenCode loads `AGENTS.md` only once per session, tell the operator to restart the session
> for the edits to take effect.

## Rules

- Read ALL specs before generating anything.
- Do NOT invent information not present in specs or existing project files.
- Ask for confirmation before writing files.
- Show a summary of what will be generated before proceeding.
