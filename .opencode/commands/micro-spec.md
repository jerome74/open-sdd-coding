---
description: "Turn a bug, error log, or small change request into a Micro-Spec patch spec under docs/specs/ and append one unchecked item to the constitution's Roadmap, ready for /SDD-implement"
argument-hint: "error log + description, or a one-line change request (omit to be asked)"
---

# Micro-Spec — Spec-Delta for post-implementation fixes

## Purpose

Kill spec friction for post-implementation fixes and polish, without losing
`docs/specs/constitution.md` as the single source of roadmap truth.

This command runs as the **primary agent**.

## Rules

Load the `sdd-guardrail` skill (`skill({ name: "sdd-guardrail" })`). It owns the Micro-Spec
template and the patch-spec skeleton; this command does not restate them.

## Input

`$ARGUMENTS` — either mode (a) an error/log/failing test plus a description, or mode (b) a
one-line change request. If empty, ask one question to get whichever the operator has.

## Step 1 — derive, don't interrogate

Deliberate deviation from `gather-requirements`'s one-question-per-message rule: friction is the
thing this feature exists to kill. Pre-fill the four Micro-Spec fields from the input:

- *Comportamento attuale* — from the quoted log/error/failing test, verbatim in a fenced block;
  from the current behavior the change request implies otherwise.
- *Comportamento atteso* — from the change request, or from what fixing the error implies.
- *Scope limitato* — from paths named in the log/description, confirmed against the filesystem
  with grep/glob. Never guess a file into scope.
- *Test di validazione* — from an existing test the log names, else a one-line manual check.

Present all four filled fields in one message and ask a single "ok / cambia X". Ask a real
question only for a field that cannot be derived from the input.

## Step 2 — delegate

Task-tool call to `@micro-spec-author` with the four confirmed fields, the proposed slug, and any
related spec/roadmap item. If the subagent channel is unavailable, run its definition inline as
"Micro-Spec authoring (embedded)", honoring the same tool restrictions — same pattern as
`SDD-implement.md`'s embedded checkpoint fallback.

## Step 3 — report

Print the patch-spec path, the exact roadmap line added, and the direct invocation
`/SDD-implement docs/specs/patch-<slug>.spec.md`. Note in one line that the item was appended at
the end of the roadmap, so `/SDD-implement 1` would pick the first pending item, not necessarily
this one.

## Interaction language

The operator's language, default Italian (matching `gather-requirements`). The patch spec itself
is written in Italian.

## Closing rules

- Never implement the fix inside this command — authoring only.
- Never check off a roadmap item — only `/SDD-implement` does that.
- Never create `constitution.md` — if it's missing, stop and point at `/init-new-project`.
- Never widen *Scope limitato* beyond what the operator confirmed.
- One Micro-Spec per invocation.
