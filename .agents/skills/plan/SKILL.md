---
name: plan
description: "Restate requirements, assess risks, and create a step-by-step implementation plan from an engineering/prompt/ file. WAIT for user confirmation before writing the plan."
metadata:
  workflow-entrypoint: "true"
---

# Codex invocation contract

Invoke as `$plan <arguments>`. This is a primary-thread workflow, not a delegable agent.
Read `.codex/instructions.md` before executing it. Source: `.opencode/commands/plan.md`.
`workflow_arguments` means the exact text after this skill mention; `workflow_arg1` means
its first positional argument. For the CLI adapter use the JSON `workflow_input.arguments`
array and its `raw` field, never re-evaluate arguments as shell code. Missing input keeps the
source workflow's question/default behavior. Skill loading performs no shell substitution.
A native `/plan` or `/init-new-project` command is not assumed to exist. Preserve every
source confirmation gate; this migration does not authorize remote effects.

# Plan Command

Create a comprehensive implementation plan before writing any code. This command runs as the
**primary agent** and delegates the drafting to the read-only `planner` subagent.

> This is an auxiliary engineering-workflow command, not part of the five-command SDD pipeline.

## Read-only delegation on Codex

The planner's role stays separate from the primary writer. Native planner delegation is
allowed only in a read-only parent session. From a writable parent use the isolated
read-only role adapter, or apply its definition as a distinct `Planning checkpoint (embedded)`
that drafts only in the reply. Preserve the explicit user confirmation before the primary
writes the engineering plan. Never treat the role TOML as a private read-only sandbox.

## Input / Output

- **Input**: a Markdown file in `engineering/prompt/`. Pass its filename as `workflow_arg1` (e.g.
  `$plan feature-x.md` reads `engineering/prompt/feature-x.md`). If `workflow_arg1` is omitted, use the most
  recently modified `*.md` file in `engineering/prompt/` (excluding `.gitkeep`). If
  `engineering/prompt/` has no Markdown files, **STOP immediately** and tell the user to add a
  prompt file first.
- **Output**: a Markdown file at `engineering/plan/<same-basename>.md` (e.g.
  `engineering/prompt/feature-x.md` → `engineering/plan/feature-x.md`) containing the confirmed
  implementation plan. The file is written **only after** the user confirms the plan — never
  before.

## What this command does

1. **Read the prompt** — load the requirement from the `engineering/prompt/` input file.
2. **Delegate drafting** — invoke `planner` (native Codex subagent tools) with the requirement. `planner` is
   read-only: it analyzes, restates requirements, breaks the work into phases with file paths and
   dependencies, assesses risks, estimates complexity, and **presents** the plan. It does not
   write anything.
3. **Present and wait** — show the drafted plan to the user and **WAIT for explicit confirmation**
   ("yes" / "proceed" / similar). If the user wants changes ("modify: …", "different approach: …",
   "skip phase 2 …"), relay them to `planner` and re-present.
4. **Write the plan** — once confirmed, the **primary agent** (not the subagent) writes the plan
   content to `engineering/plan/<same-basename>.md` and confirms the saved path.

## When to use

- Starting a new feature
- Significant architectural changes
- Complex refactoring
- Multiple files/components affected
- Requirements are unclear or ambiguous

## Plan shape

`planner` produces the plan in the format its own definition specifies (Overview · Requirements ·
Architecture Changes · Implementation Steps by phase, each step with file path / action / why /
dependencies / risk · Testing Strategy · Risks & Mitigations · Success Criteria).

## Important

**CRITICAL**: no plan file is written to `engineering/plan/` until the user explicitly confirms
the plan. `planner` cannot write it (read-only); the primary agent writes it after confirmation.

## Related

- Subagent: `planner` (`.codex/agents/planner.toml`) — read-only; drafts and presents, never
  writes.
- `$sdd-prompt-engineering` produces the `engineering/prompt/<slug>.md` files this command reads.
