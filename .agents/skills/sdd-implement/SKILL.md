---
name: sdd-implement
description: "Execute a Specification-Driven Development roadmap: resolve roadmap items from the constitution, plan, produce deliverables (code, tests, docs, infra, config, diagrams, schemas, and more), validate, and publish \u2014 one item at a time, with governance over every produced artifact type"
metadata:
  workflow-entrypoint: "true"
---

# Codex invocation contract

Invoke as `$sdd-implement <arguments>`. This is a primary-thread workflow, not a delegable agent.
Read `.codex/instructions.md` before executing it. Source: `.opencode/commands/SDD-implement.md`.
`workflow_arguments` means the exact text after this skill mention; `workflow_arg1` means
its first positional argument. For the CLI adapter use the JSON `workflow_input.arguments`
array and its `raw` field, never re-evaluate arguments as shell code. Missing input keeps the
source workflow's question/default behavior. Skill loading performs no shell substitution.
A native `/plan` or `/init-new-project` command is not assumed to exist. Preserve every
source confirmation gate; this migration does not authorize remote effects.

# SDD-Implement — Conductor

You are the **Conductor**: this command runs as the **primary agent**, never as a subtask. You orchestrate the SDD cycle for roadmap items and turn each into **whatever deliverables its spec requires** (code, tests, docs, infra, config, diagrams, schemas, migrations, scripts, …). Documentation is one possible deliverable, not the goal; the spec decides. You delegate only specialist checkpoints via native Codex subagent tools — never the orchestration.

Priorities, in order: (1) faithful realization of the spec; (2) traceability roadmap → artifacts; (3) consistency across the item's deliverables; (4) governance of every artifact type; (5) knowledge capture.

## Sources

- `docs/specs/constitution.md` — single source of truth: `## Roadmap` (`- [ ]` pending, `- [x]` done; order = execution order), Mission principles and Tech Stack constraints binding every deliverable. Missing → bootstrap condition: report roadmap not initialized, point to `$init-new-project`, never invent a roadmap.
- `docs/specs/*.spec.md` — each spec declares its deliverables and acceptance criteria.
- `docs/plan/` — every item's plan is written here before any deliverable. Create the folder if missing (never a blocker).
- Artifact destinations — from the spec and project conventions; none is privileged.
- **Declared structure** — the shape a spec section, a plain project template, or a stated convention defines for an artifact type. No template engine exists.

## Input (`workflow_arg1`)

| Input | Meaning |
|---|---|
| spec path (e.g. `docs/specs/03-feature.spec.md`) | that spec |
| number `N` | next N unchecked items, in order |
| `-all` | all unchecked items, in order |

No argument → ask which mode.

## Mandatory constraints

1. **Roadmap-grounded** — every execution starts from an unchecked roadmap item and its linked spec. No untraceable work.
2. **Plan first** — `docs/plan/{id}-{name}.plan.md` exists and is approved before any deliverable. No plan = no deliverable.
3. **Spec-driven, not template-driven** — derive deliverables from spec + constitution (+ architecture/standards the spec references). A template is an optional input for document deliverables only.
4. **Single source of truth** — build only what spec and constitution define; never invent components, interfaces, layers, structure, topology. Missing information → stop and ask.
5. **Discovered, not hardcoded** — capabilities under `.opencode/` resolve at runtime by declared role and metadata, never by filename. This prompt names no asset; adding an asset must never require editing it.
6. **Bindings recorded** — every bound capability is written in the plan and approved with it. Never bind silently mid-production.
7. **Governed delivery** — nothing is published without passing its validation and publication gates.
8. **One item at a time** — complete plan → produce → validate → publish for an item before starting the next. A dependency on an undelivered spec → flag it and ask.

## Governance

**Delivery Governance** applies to every artifact type at the validation and publication gates: requirements (real unchecked roadmap entry + readable spec), specification (deliverables, interfaces, acceptance criteria defined), architecture compliance (Tech Stack, mandatory patterns), code compliance (project standards, bound instructions, existing patterns), documentation compliance (required structure), traceability, artifact completeness (every required deliverable exists or its gap is reported), publication approval.

**Structure-governance checkpoint** — required only when the item has an artifact with a declared structure.
- Select the governance agent **by role**: the registry agent whose `description` declares it governs/validates declared-structure fidelity on produced artifacts and does **not** generate content. More than one candidate → ask.
- **Delegated mode (preferred):** invoke it via native Codex subagent tools and consume its report. **Embedded mode (fallback, no subagent channel):** do not stop or ask for a waiver — load its definition and run it yourself, verbatim, as a step labeled `Governor checkpoint (embedded)`, honoring its read-only restrictions. Both modes carry identical authority.
- No governance agent in the registry → run the checkpoint's intent inline under Delivery Governance, record the gap in the plan, never invent structure.
- Findings and approval are authoritative. A **critical failure** (structure / traceability / completeness) stops that deliverable: surface it.

**Traceability chain** — every artifact links back through:
`Roadmap Entry → Specification → Capability Bindings → Planned Work → Produced Artifacts → Validation → Publication`.
Capability Bindings make discovery auditable: without them a re-run could bind different assets with no trace.

## Process

Phase 0 runs once per invocation; phases 1–5 run per item.

### Phase 0 — Discover capabilities

1. Scan metadata only: `.codex/agents/*.toml` (TOML name, description),
   `.agents/skills/*/SKILL.md` (YAML name, description, metadata), `.codex/config.toml`.
   Follow skill symlinks without scanning the original directories a second time.
   Read bodies only in Phase 2 after capability shortlisting. Ignore scripts/resources,
   caches, fixtures and nested noncanonical SKILL.md files.
2. Classify by metadata: native TOML with name/description/developer_instructions is an
   agent role; SKILL.md with metadata.workflow-entrypoint=true is a command reference,
   never an artifact producer; other SKILL.md entries are reusable skills/constraints.
   Missing/invalid metadata is undiscoverable, never guessed from a filename.
3. Record path, kind, name, purpose, applicability and negative triggers. Bind nothing yet.
4. Native metadata unavailable: use `.codex/capability-registry.md` as the role-based fallback.
   Empty/unreadable registry: proceed on spec + constitution and report reduced capability.
   No matching specialized skill: produce from spec/constitution and record the gap.
   No governance role: apply Delivery Governance inline; never skip the gate.
   No declared structure: stop and ask. Negative triggers remain hard vetoes.
5. Read-only native roles require a read-only parent. For a writable Conductor use the
   source-defined embedded checkpoint or an isolated read-only role session; never spawn
   a read-only role into a writable parent and claim its TOML enforces isolation.

### Phase 1 — Resolve input

1. Parse `## Roadmap` in the constitution (absent → bootstrap condition, stop).
2. Select items: spec path → must exist with an unchecked item · `N` → first N unchecked · `-all` → all unchecked.
3. For each, read its spec and list the **deliverable types** it requires.
4. Prepare context: specs, roadmap entries, deliverable types, applicable constitution rules, source inputs.

### Phase 2 — Plan

Write `docs/plan/{id}-{name}.plan.md` with:
- **Deliverable inventory** (first — bindings resolve against it): every artifact, type, target location.
- **Capability Bindings** (below).
- Tasks: implementation (code/APIs/schemas/migrations), documentation, testing (mapped to acceptance criteria), infra & config.
- Dependencies, risks + mitigation, validation criteria ("done" for the item), delivery order (code-first / docs-first / parallel — driven by the spec).

**Binding rules:**
- **Scope-scoped skills bind as constraints**: every skill whose declared scope covers an artifact's path binds; all matches apply cumulatively. Conflict → a skill declaring itself single source of truth for its domain wins; else the narrower scope; else ask.
- **Skills/agents bind by capability match**: shortlist on frontmatter, read full definitions only for the shortlist. **Negative triggers are hard vetoes.** Exactly **one producer** per artifact; governance agents validate, never produce. Two plausible candidates with no veto → ask.
- **Commands never bind** and are never invoked.

Record bindings as:

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| *artifact + target path* | *registry path* | skill / agent | *matched scope or capability* | *vetoes, rejected alternatives, gaps* |

Also record deliverables with no bound capability (with the ladder step applied) and bindings that needed a question.

Declared-structure artifact planned → run the structure-governance checkpoint now and record: applicable structure, suitability, mandatory sections, required deliverables, dependencies.

Present the plan **with the bindings table** for user approval before Phase 3. The approval gate is what makes runtime discovery safe.

### Phase 3 — Produce

Produce each deliverable through its **bound capability** and within its **bound constraints**. A capability the plan missed → stop, amend the plan, re-approve.
- Code/APIs/schemas/migrations: per spec + Tech Stack, bound instructions, existing patterns; surgical, minimal changes.
- Tests: those in the plan, exercising the acceptance criteria.
- Documents: per required structure. Declared-structure documents: obtain structure selection/constraints from the checkpoint first, then populate it — never select structure outside the checkpoint.
- Infra/config/scripts/operational artifacts: per spec and referenced standards.
- Diagrams: Mermaid in Markdown, a real type per diagram (`flowchart`, `sequenceDiagram`, `erDiagram`, …), only from models the spec documents (context, component, sequence, data flow, ER, deployment). Information missing → omit and record the gap.
- Label every assumption; never present inference as fact. Keep deliverables consistent.

### Phase 4 — Validate

- Code: run the plan's tests, verify acceptance criteria end-to-end, check architecture/code compliance. Fix failures at the root.
- Documents: completeness, required sections, metadata, terminology; declared-structure → checkpoint report.
- Infra/config/scripts: lint, dry-run, schema checks as applicable.
- Bound-constraint compliance; traceability (chain recoverable, producers/governors = approved bindings); completeness.

Any failure, missing deliverable, unresolved assumption, broken traceability, artifact produced outside its binding, or checkpoint critical failure → back to Phase 3. Output: per-deliverable result + item pass/fail.

### Phase 5 — Publish & update

Gate: item passed Phase 4; declared-structure documents also need checkpoint approval (validation passed, structure satisfied, traceability complete, no critical issue). Gate fails → back to Phase 3/4, publish nothing.

After the gate: save deliverables to their targets; update indexes and cross-references; record capability gaps and follow-ups in the delivery history; flip the item `- [ ]` → `- [x]` in `## Roadmap`; update the spec's status with brief notes. Edit constitution and specs in their own language (Italian).

### Session hygiene — between items

Context from a finished item is dead weight for the next. When `N > 1` or `-all` leaves further unchecked items after Phase 5:
1. **Stop** and report: item completed, items remaining.
2. Tell the operator to run `/compact` (or open a new session) and then reply to continue — or re-run `$sdd-implement <remaining N | -all>` in a fresh session.
3. On resume: re-read `## Roadmap` from the constitution (the only state); re-run Phase 0 only if the registry is no longer in context.

Never start the next item in the same uncompacted context.
