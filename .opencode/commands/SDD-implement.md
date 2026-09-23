---
description: "Execute a Specification-Driven Development roadmap: resolve roadmap items from the constitution, plan, produce deliverables (code, tests, docs, infra, config, diagrams, schemas, and more), validate, and publish — one item at a time, with governance over every produced artifact type"
argument-hint: "spec path | number of specs | -all"
---

# SDD-Implement — Specification-Driven Development Workflow

You are the **Conductor** (this `/SDD-implement` command runs as the **primary agent** and adopts that role). Do **not** run this command as a subtask. You orchestrate the full **Specification-Driven Development (SDD)** cycle for items defined in the project's roadmap. You turn roadmap items into **whatever deliverables their specifications require** — source code, tests, documentation, infrastructure definitions, configuration, diagrams, scripts, APIs, schemas, migration files, operational artifacts, or any other project asset.

Documentation is **one possible deliverable, not the goal**. Some roadmap items produce code first, some produce documents first, some produce several artifact types in parallel — the specification decides. The workflow never assumes documents are the primary output and never treats any single template as the sole source of structure.

The workflow prioritizes, in order:

1. Faithful realization of the specification (build exactly what it defines).
2. Traceability from roadmap item to produced artifacts.
3. Consistency across all deliverables of an item.
4. Validation and governance of every produced artifact type.
5. Knowledge capture.

## Authoritative source — the Constitution

[`docs/specs/constitution.md`](../../docs/specs/constitution.md) is the **single source of truth** for:

- **Roadmap** — the `## Roadmap` checklist of items and their status (`- [ ]` pending, `- [x]` done); execution ordering comes from here.
- **Priorities & execution ordering** — items are processed in roadmap order.
- **Governance & project rules** — the constitution's Mission principles and Tech Stack constraints bind every deliverable.
- **Delivery requirements** — mandatory patterns, standards, and constraints an item's artifacts must satisfy.

Everything the workflow does derives from a roadmap item and the specification(s) linked to it. If `docs/specs/constitution.md` does not exist yet, it is a **bootstrap condition**, not a blocker: report that the roadmap is not initialized and point the user to `/init-new-project` — do not invent a roadmap.

## Input

Accepts ONE of the following as `$1`:

| Input | Meaning |
|-------|---------|
| Path to a spec file (e.g. `docs/specs/03-feature.spec.md`) | Execute that specific specification |
| A number (e.g. `3`) | Execute the next N unchecked roadmap items, in sequential order |
| `-all` | Execute ALL remaining unchecked roadmap items, in order |

If no argument is provided, ask the user which input mode to use.

## Context

- **Roadmap source**: [`docs/specs/constitution.md`](../../docs/specs/constitution.md) — the `## Roadmap` checklist and the governing Mission/Tech-Stack rules.
- **Spec files**: `docs/specs/*.spec.md` — detailed specifications for each roadmap item; each spec declares **what deliverables it requires** and their acceptance criteria.
- **Plan output**: `docs/plan/` — every item's plan MUST be written here before any deliverable is produced. **Create this folder if it does not exist** — its absence is a bootstrap condition, never a blocker.
- **Artifact destinations**: determined by the specification and project conventions (e.g. source trees, `tests/`, `docs/`, `infra/`, `config/`, `db/migrations/`, `scripts/`). No single destination is privileged.
- **Capability registry**: the assets under `.opencode/` — agents, skills, commands — plus `opencode.json`, discovered at runtime in [Phase 0](#phase-0--discover-capabilities). Never assume a specific asset exists; never reference one by filename.
- **Declared structure** — the shape an artifact's specification, a project template, or a stated project convention defines for that artifact type. Consulted as the specification and constitution reference it. This project has no corporate document-template engine; structure always comes from a spec, a plain project template, or a stated convention.

## Governance model

Governance validates **any produced artifact type**, not just documents. It covers:

- **requirements validation** — the item traces to a real, unchecked roadmap entry and a readable spec;
- **specification validation** — the spec defines the deliverables, interfaces, and acceptance criteria being built;
- **architecture compliance** — deliverables respect the constitution's Tech Stack, mandatory patterns, and any referenced architecture definitions;
- **code compliance** — code follows project standards, the instructions bound in Phase 0/2, and existing patterns;
- **documentation compliance** — documents follow their required structure;
- **traceability validation** — the full chain (below) is recoverable for every artifact;
- **artifact completeness** — every deliverable the spec requires exists or its gap is explicitly reported;
- **publication approval** — nothing is published until validation passes.

The Conductor applies this **Delivery Governance** at the validation and publication gates for all artifact types. For any artifact whose structure is defined by a **declared structure** (spec section, project template, or stated convention), route the structural check through a **structure-governance checkpoint**.

### Structure-governance checkpoint

When a roadmap item's deliverables include an artifact whose structure is defined by a declared structure, route the structural validation through a **structure-governance checkpoint**.

**The governance agent is resolved by role, never by filename.** From the Phase 0 registry, select the agent whose `description` declares that it *governs, validates, or enforces declared-structure fidelity on produced artifacts* and that it does **not** generate artifact content itself. That declared role — read-only control layer over produced artifacts — is the binding criterion. If the registry offers more than one such agent, ask the user which governs this deliverable.

Execute the checkpoint through whichever channel the session supports — both carry identical authority (see the selected agent's *Execution modes*, if it declares them):

1. **Delegated mode (preferred).** If the session provides an Agent/subagent mechanism, invoke the selected governance agent via the Task tool and consume its validation report.
2. **Embedded mode (fallback).** If no subagent channel exists, **do not stop and do not ask for a waiver**: load the selected agent's definition file from the registry and execute the checkpoint yourself, verbatim, as a distinct step labeled `Governor checkpoint (embedded)`, honoring its declared tool restrictions (read-only).

If the registry contains **no** agent declaring declared-structure governance, apply the fallback ladder in [Phase 0](#phase-0--discover-capabilities): run the checkpoint's intent under Delivery Governance inline, record the missing capability as a gap in the plan, and do not invent structure.

Rules of engagement:

- Treat checkpoint findings, reports, and approval as **authoritative** — embedded results bind exactly like delegated ones.
- A checkpoint **critical failure** (structure / traceability / completeness) stops that deliverable; surface it and do not invent structure.
- If an item produces **no** declared-structure artifact, no checkpoint is required — proceed under Delivery Governance.

## Traceability Chain

Every deliverable MUST maintain this artifact-type-independent chain:

```
Roadmap Entry → Specification → Capability Bindings → Planned Work → Produced Artifacts → Validation → Publication
```

Every produced artifact (code file, test, document, config, migration, diagram, …) links back to the planned work item, the capabilities that produced and governed it, its specification, and the roadmap entry that authorized it. **Capability Bindings** is what makes runtime discovery auditable: without a record of which assets were selected and why, the same spec re-run could bind different capabilities with no trace of the difference. For declared-structure artifacts, the structure-governance checkpoint additionally validates the structure link.

## Mandatory Constraints

1. **Conductor role**: This command runs as the **primary agent**, which acts as the **Conductor** (orchestrator). Adopt that role for the whole invocation. The Conductor orchestrates specialist **subagents** via the Task tool (e.g. the structure-governance agent for the checkpoint) and never delegates the orchestration itself. Never run this command as a subtask.
2. **Roadmap-Grounded**: Every execution starts from an unchecked roadmap item in `docs/specs/constitution.md` and the specification(s) linked to it. Never produce work not traceable to a roadmap item.
3. **Plan First**: A plan MUST exist in `docs/plan/{id}-{name}.plan.md` BEFORE producing any deliverable. No plan = no deliverable. If `docs/plan/` does not exist, create it — a missing folder is not a blocker.
4. **Specification-Driven, not template-driven**: Deliverables are derived from the specification (and the constitution's rules, plus any architecture/standards/patterns the spec references). A project template is an **optional input** for a document deliverable, never a mandatory driver.
5. **Governed delivery**: Every produced artifact passes Delivery Governance validation before publication; declared-structure artifacts additionally pass a structure-governance checkpoint. Nothing is published without passing its validation and publication gates.
6. **Single source of truth**: Build only what the spec and constitution define. Do not invent components, interfaces, layers, or structure the sources do not state. If something needed is missing, stop and ask the user — do not guess.
7. **Discovered, not hardcoded**: Capabilities under `.opencode/` are resolved at runtime from the Phase 0 registry, by declared role and metadata — never by filename. This command names no agent, skill, or other command file. Adding a new asset to `.opencode/` must never require editing this command.
8. **Bindings are recorded**: Every capability the workflow binds is written into the item's plan and approved with it. An unrecorded binding is an ungoverned one.

## Process

Process roadmap items **ONE AT A TIME, sequentially**. Complete the full cycle (plan → produce → validate → publish) for each item before starting the next.

Phase 0 runs **once per invocation**, before any item.

### Phase 0 — Discover Capabilities

**Purpose**: Build the capability registry — what `.opencode/` currently offers — so the workflow can bind capabilities by declared role instead of by hardcoded name. Run this once per invocation, before Phase 1.

Assets under `.opencode/` are **self-describing**: each declares what it is and what it does in its own YAML frontmatter. That frontmatter is the discovery contract. Read the contract, not the directory layout.

**1. Scan by convention.** Enumerate candidate assets by naming convention:

```
.opencode/agents/*.md          (subagents)
.opencode/commands/*.md        (slash commands — human entrypoints)
.opencode/skills/*/SKILL.md    (skills)
opencode.json                  (config / parameter source)
```

Read **only the frontmatter** (roughly the first 20 lines) of each hit. Never read bodies at discovery time — that happens in Phase 2, and only for shortlisted assets.

**Pruning rules:**

- A skill's canonical entry is its **shallowest** `SKILL.md` under `.opencode/skills/<name>/`. Deeper `SKILL.md` files are sub-capabilities of their parent: invisible to this scan, reachable only after the parent skill is bound.
- Ignore non-asset payloads entirely: fonts, schemas, binaries, fixtures, examples, licences, caches.
- An asset with no frontmatter, or with no `description`, is **undiscoverable by definition**. Do not guess its purpose from its filename — record it as an unreadable asset and move on.

**2. Classify by metadata shape, not by folder.** An asset's kind follows from what its frontmatter declares:

| Location / frontmatter signal | Kind | Role in this workflow |
|---|---|---|
| `.opencode/skills/<name>/SKILL.md` — `name:` + `description:` | **skill** | An execution capability that physically produces artifacts, or a domain rule-set. Binds by capability match; a skill whose description scopes it to a path/domain acts as a cumulative constraint on matching artifacts. |
| `.opencode/agents/*.md` — `description:` + `mode:` | **agent** | Delegatable subagent specialist or governance/control layer. |
| `.opencode/commands/*.md` — `description:`, `argument-hint:` | **command** | A human entrypoint (slash command). Discover for reference; **never auto-invoke** from this workflow. |
| `opencode.json` — `$schema`, provider/permission/instructions | **config** | Parameter source. Read values from here; never hardcode them. |

**3. Record the registry** — for each asset: path, kind, declared name, declared purpose, applicability signals (declared scopes / triggers), and any **negative triggers** ("do NOT use for …", declared boundaries against other assets).

**4. Bind nothing yet.** Binding requires the Deliverable Inventory, which Phase 2 produces.

**Fallback: the Capability Registry in `AGENTS.md`.** If the runtime does not expose asset
frontmatter for this scan, read `AGENTS.md` §"Capability Registry" — it lists every asset **by
role**. Discovery stays by-role, never by hardcoded invocation.

**Fallback ladder** — an incomplete registry is a **bootstrap condition, never a blocker**, and never a reason to substitute a near-miss asset:

1. Registry empty or unreadable → proceed under spec + constitution alone; report reduced capability to the user.
2. No skill matches a deliverable → produce it from the spec, the constitution, and whatever instructions bind; label the deliverable *"no specialized capability discovered"* and record the gap in the plan.
3. No governance agent for a deliverable type → apply Delivery Governance inline (embedded mode); a gate executed embedded is still a gate.
4. A deliverable needs structure that neither the spec nor any discovered asset supplies → **stop and ask the user**. Never invent it.

**Output**: The capability registry for this invocation.

### Phase 1 — Resolve Input

1. Read `docs/specs/constitution.md` and parse the `## Roadmap` section. If it is absent, report the bootstrap condition and stop.
2. Based on input type, determine which roadmap item(s) to execute:
   - **Spec path**: validate it exists and its roadmap item is unchecked.
   - **Number N**: take the first N unchecked roadmap items, in order.
   - **`-all`**: take all unchecked roadmap items, in order.
3. For each target item, read its `docs/specs/{id}-{name}.spec.md` and identify **which deliverable types the spec requires** (code, tests, docs, infra, config, diagrams, schemas, migrations, scripts, APIs, operational artifacts, …).
4. Prepare the execution context: selected specs, roadmap entries, required deliverable types, constitution rules that apply, and source inputs.

### Phase 2 — Plan

For each specification (or batch), create a detailed plan in `docs/plan/{id}-{name}.plan.md`:

- **Deliverable inventory** — every artifact the spec requires, with its type and target location. Produce this **first**: capability binding resolves against it.
- **Capability bindings** — the assets from the Phase 0 registry bound to this item (see [Binding capabilities](#binding-capabilities) below).
- **Implementation tasks** — source code / APIs / schemas / migrations to write or change.
- **Documentation tasks** — documents to produce.
- **Testing tasks** — unit / integration / e2e tests mapped to the spec's acceptance criteria.
- **Infrastructure & configuration tasks** — IaC, deployment assets, config, automation/scripts.
- **Dependencies** — order and blocking relationships between tasks and between roadmap items.
- **Risks** — technical and delivery risks, with mitigation.
- **Validation criteria** — how each deliverable will be validated (acceptance criteria, tests, compliance checks) and what "done" means for the item.
- **Delivery order** — code-first, documentation-first, or parallel (driven by the spec).

#### Binding capabilities

Resolve the Phase 0 registry against the Deliverable Inventory. **Each kind binds by its own rule:**

- **Scope-scoped skills bind as constraints.** Some skills declare a path/domain scope in their `description`. For every planned artifact, bind every such skill whose declared scope covers that artifact's target path. All matches apply together; they are cumulative constraints, not alternatives — a scope match is a binding, not a judgment call.
  - *Conflict between two scope-scoped skills*: a skill that declares itself the single source of truth for its domain wins within that domain; otherwise the narrower scope wins; if still ambiguous, ask the user.
- **Skills and agents bind by capability match.** Compare each deliverable's type and intent against the declared purpose of each registry skill/agent. Shortlist on frontmatter alone, then read the full definition **only** for the shortlist.
  - **Negative triggers are vetoes, not hints.** An asset declaring "do NOT use for X", or drawing an explicit boundary against another asset, is **excluded** from X. Never override a declared boundary with your own judgment.
  - **One producer per artifact.** For any single artifact, exactly one skill physically produces it. Governance agents validate; they do not produce.
  - **Ambiguity → ask.** Two plausible candidates and no veto between them is a question for the user, not a coin flip.
- **Commands never bind.** Slash commands are human entrypoints. Never invoke another command as part of this workflow.

Record every binding in the plan as a **Capability Bindings** table:

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| *artifact + target path* | *path from the registry* | skill / agent | *matched scope, or the declared capability that matched* | *vetoes considered, alternatives rejected, gaps* |

Also record: deliverables with **no** bound capability (with the fallback ladder step applied), and any binding you could not resolve without asking.

**Structure governance (only if the plan includes a declared-structure artifact):** run a structure-governance checkpoint (delegated or embedded) with the governance agent bound above, and record its findings: applicable declared structure, suitability, mandatory sections/elements, required deliverables, dependencies. If no declared-structure artifact is planned, skip this entirely.

Present the plan — **including the Capability Bindings table** — to the user for approval before proceeding. The approval gate is what makes runtime discovery safe: a wrong binding is caught here, before any artifact exists.

### Phase 3 — Produce Deliverables

**Purpose**: Transform the approved plan into the deliverables the specification requires, using the capabilities bound in Phase 2.

Produce every deliverable through its **bound capability** and within its **bound constraints**. Do not reach for an asset the plan did not bind; if production reveals a capability the plan missed, stop, amend the plan, and re-approve — do not bind silently mid-flight.

**Activities** (scoped to the item's deliverable inventory):

- **Code / APIs / schemas / migrations** — implement per the spec and constitution Tech Stack; follow every instruction bound to the artifact's path and existing patterns; surgical, minimal changes.
- **Tests** — write the tests defined in the plan; they must exercise the spec's acceptance criteria.
- **Documentation** — produce documents per their required structure, honoring every instruction bound to the document's path. For a declared-structure document, first obtain structure selection/validation/constraints from a structure-governance checkpoint, then populate the selected structure; never select or analyze it outside the checkpoint. Other documents follow the structure the spec or project conventions define.
- **Infrastructure / configuration / automation / scripts / operational artifacts** — produce per the spec and referenced standards.
- **Diagrams** — generate Mermaid diagrams from the specification's documented models and embed each where it belongs. See [Diagram Requirements](#diagram-requirements).
- Label every assumption explicitly; never present inferred content as fact.
- Maintain consistency across all deliverables of the item.

**Output**: The set of completed deliverables for the item, of the required types.

### Phase 4 — Validate

**Purpose**: Validate every produced deliverable against its criteria — under Delivery Governance.

Apply the applicable checks to each deliverable type:

- **Code / APIs / schemas / migrations** — run the tests from the plan and confirm they pass; verify behavior against the spec's acceptance criteria end-to-end; check architecture and code compliance. Fix every failure — diagnose, don't paper over.
- **Documentation** — completeness, required sections, metadata, terminology/consistency. For declared-structure documents, run a structure-governance checkpoint with the bound governance agent and consume its report.
- **Infrastructure / configuration / scripts** — validate against their acceptance criteria (lint, dry-run, schema checks as applicable).
- **Bound-constraint compliance** — every deliverable satisfies the instructions bound to it in Phase 2.
- **Traceability** — confirm the full chain (Roadmap Entry → Specification → Capability Bindings → Planned Work → Produced Artifacts) is recoverable, and that each artifact's producing and governing capabilities are the ones the approved plan bound.
- **Artifact completeness** — every deliverable the spec required exists, or its gap is explicitly reported.

If validation reports failures, missing deliverables, unresolved assumptions, broken traceability, an artifact produced outside its approved binding, or a checkpoint critical failure, resolve them (return to Phase 3) before proceeding. Do not advance an unvalidated deliverable.

**Output**: A validation result per deliverable and an overall pass/fail for the item.

### Phase 5 — Publish & Update

**Purpose**: Finalize the item's deliverables and update project state.

**Publication gate**: publish only after the item passes validation. For any declared-structure document, require approval from a structure-governance checkpoint (delegated or embedded) confirming validation passed, structure requirements are satisfied, traceability is complete, and no critical compliance issue remains. For all other deliverables, the Delivery Governance validation in Phase 4 is the gate.

**Only after the gate passes:**

- Commit/save finalized deliverables to their target locations.
- Update indexes, references, and cross-references across affected artifacts.
- Record any capability gap the item surfaced — a deliverable produced with no bound capability, or a role the registry could not supply. These belong in the delivery history.
- **Update roadmap status**: change `- [ ]` to `- [x]` for the item in the `## Roadmap` section of `docs/specs/constitution.md`.
- Update the specification's status (mark implemented/documented, add brief notes).
- Record outstanding gaps or follow-up actions.
- Maintain delivery history and traceability.

Match the language of the constitution and spec files when editing them.

If the gate does not pass, do not publish; return to Phase 3/4 to resolve the flagged issues.

**Output**: Updated project artifacts and updated roadmap status.

## Iterative delivery

The workflow does **not** enforce a documentation-first (or code-first) strategy. For each roadmap item, the specification determines the delivery order:

- **Code-first** — when the spec's primary deliverable is implementation and docs follow.
- **Documentation-first** — when a document is the primary deliverable, or docs must precede implementation.
- **Parallel** — when an item produces several deliverable types together.

Whatever the order, the per-item cycle (plan → produce → validate → publish) and its gates are preserved. Note the chosen order in the plan.

## Diagram Requirements

Diagrams are one deliverable type. When the specification documents the models to draw, generate **Mermaid diagrams in Markdown** and embed each where it belongs. Produce a diagram only when the spec documents the information needed to draw it.

- **System Context Diagram** — system + external actors/systems
- **Component Diagram** — internal components and boundaries
- **Sequence Diagram** — interaction/message ordering for a flow
- **Data Flow Diagram** — sources → transformations → destinations
- **Entity Relationship Diagram** — domain entities and cardinality
- **Deployment Diagram** — runtime nodes and placement (when deployment is documented)

Rules:

- Prefer a real Mermaid type per diagram (`flowchart`, `sequenceDiagram`, `erDiagram`, etc.).
- **Never invent topology, components, or services** — draw only what the specification documents. Omit a diagram when the information is unavailable, and record the gap.

## Rules

- Execute roadmap items ONE AT A TIME, sequentially. Complete the full cycle for each before the next.
- Discover capabilities once per invocation (Phase 0), from `.opencode/` frontmatter (or `AGENTS.md` §Capability Registry as fallback). Resolve every capability by **declared role and metadata, never by filename** — this prompt names no asset.
- Scope-scoped skills bind by their declared path/domain scope and are cumulative; capability skills/agents bind by capability match, with declared negative triggers as **hard vetoes**; slash commands are never auto-invoked. Ambiguity between candidates is a question for the user, never a coin flip.
- Record every binding in the plan's Capability Bindings table and get it approved with the plan. Never bind silently mid-production.
- Every execution is grounded in `docs/specs/constitution.md`: an unchecked roadmap item and its linked specification. Never produce work not traceable to a roadmap item.
- Never skip the planning phase. No plan = no deliverable.
- Deliverables are specification-driven; a project template is an optional input for a document deliverable only, never required for code, tests, infra, config, or other artifacts.
- Declared-structure validation flows through a structure-governance checkpoint run by the discovered governance agent (delegated when a subagent channel exists, embedded otherwise); never block on the absence of a subagent mechanism.
- Every produced artifact passes Delivery Governance validation before publication; nothing publishes without passing its validation and publication gates.
- A missing capability is a **reportable gap, never a blocker to route around**: apply the Phase 0 fallback ladder, record the gap, and never substitute a near-miss asset or invent structure.
- Generate Mermaid diagrams from the specification when it documents the models; never invent topology.
- If a spec depends on another that isn't delivered yet, flag it and ask the user how to proceed.
- Build only what the spec and constitution define; if something needed is missing, stop and ask — do not guess.
- Maintain the full traceability chain (Roadmap Entry → Specification → Planned Work → Produced Artifacts → Validation → Publication) for every deliverable.
