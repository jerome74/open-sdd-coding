---
name: sdd-guardrail
description: >-
  Keeps changes inside Spec-Driven Development — refuses direct code/config edits requested by a
  plain chat message that is not issued through a command and is not a request for an explanation,
  and routes them to /micro-spec instead. Owns the Micro-Spec (Spec-Delta) four-field template,
  the Append-Only pattern, and the Error-to-Spec conversion rules. Use when someone asks to "just
  fix", "just tweak", "quickly change" something in chat; when writing or reviewing a patch spec.
  Do NOT use as a substitute for a full docs/specs/*.spec.md on a substantial feature.
---

# SDD Guardrail

## Scope

This skill is the single source of rules for the Micro-Spec technique family. `/micro-spec` and
`micro-spec-author` reference it and must not restate the template, the guardrail wording, or the
Append-Only / Error-to-Spec guidance below. If a rule conflicts, this skill wins.

## The guardrail

> **Rule.** When a request to change code, configuration, or content arrives as a plain chat
> message — not issued through a command — and is not a request for an explanation (reading,
> searching, explaining, reviewing, diagnosing), do not make the change. In every other case the
> guardrail fires. Answer in one short message that names what is missing and offers the fastest
> legal route:
> *"Questa richiesta non passa da un comando. Posso trasformarla in una Micro-Spec con
> `/micro-spec <descrizione>` e poi eseguirla con `/SDD-implement docs/specs/patch-<slug>.spec.md`.
> Procedo?"*
>
> **The guardrail never fires on** (only these two — it is a brake, not a lock):
> - anything that produces no edit — reading, searching, explaining, reviewing, diagnosing;
> - work already issued through a command — `/SDD-implement`, `/spec-brainstorm`,
>   `/gather-requirements`, `/init-new-project`, `/micro-spec`, or any other command — those flows
>   carry their own gate.
>
> No other exemption exists — not the SDD scaffolding itself (`.opencode/**`, `docs/specs/**`,
> `AGENTS.md`, `opencode.json`, ...), not an operator override typed in chat. A plain chat message
> requesting any such edit fires the guardrail like any other; the only way through is
> `/micro-spec` (or the relevant command).

## The Micro-Spec template

Four Italian fields — `/micro-spec` fills what it can derive from the input and asks only for
what it cannot:

- **Comportamento attuale** — what happens today (the bug, the wrong behavior, the state before
  the change). If the input is a log/error/failing test, quote it verbatim in a fenced code block
  here — never paraphrase it away.
- **Comportamento atteso** — what should happen once the fix lands.
- **Scope limitato** — the exact list of files the fix may touch. No file outside this list may be
  modified; this is the deliverable inventory `/SDD-implement` plans from.
- **Test di validazione** — how to verify the fix worked: an existing test the input names, or a
  one-line manual check.

Patch-spec file skeleton (written by `micro-spec-author` to `docs/specs/patch-<slug>.spec.md`):

```markdown
# Micro-Spec: <titolo breve>

> Patch scoped — non sostituisce una spec completa. Generata da `/micro-spec` il <YYYY-MM-DD>.
> Per il Conductor: **Scope limitato** è l'inventario dei deliverable di questa voce.
> Nessun file fuori da quell'elenco può essere modificato.

## Comportamento attuale
## Comportamento atteso
## Scope limitato
## Fuori scope
Qualsiasi file non elencato sopra. Se la correzione ne richiede uno, fermarsi e riportare — non allargare lo scope.
## Test di validazione
## Acceptance criteria
### AC-01
Dato <contesto>, quando <azione>, allora <risultato atteso>.
## Origine
Spec/voce correlata: <link o "nessuna"> · Input: <error log | richiesta di modifica> · Data: <YYYY-MM-DD>
```

The `## Acceptance criteria` / `AC-01` shape mirrors `docs/templates/template.spec.md` so
`/SDD-implement` Phase 4 finds acceptance criteria where it expects them — a restatement of
*Test di validazione* in Given/When/Then, not a new field for the caller to fill.

## When Micro-Spec is the wrong tool

Non-enforced guidance, not a gate — no criterion here blocks `/micro-spec` from running. The
operator decides case by case whether a change belongs in a Micro-Spec or a full
`docs/specs/*.spec.md`. A Micro-Spec is shaped for a fix that:

- touches roughly a handful of files, all already existing;
- introduces no new component, module, public interface, endpoint, or dependency;
- changes no data model, schema, migration, or persisted contract;
- is verifiable by one test or one manual check statable in a single sentence.

When a request clearly outgrows this shape, say so and suggest `/spec-brainstorm` (or
`/gather-requirements` for a new capability) — but the operator's explicit choice to proceed with
`/micro-spec` anyway is final; this is a reference, not a rule the command enforces.

## Append-Only

A manual technique, not automated: adding a new unchecked `- [ ]` sub-item inside an *existing*
spec file rather than authoring a new patch spec, when the fix is a small addendum to work already
described there.

**Incompatibility warning.** `/SDD-implement` is roadmap-driven — it reads `## Roadmap` in
`docs/specs/constitution.md`, not the internals of already-`- [x]`-ed spec files. A checkbox
appended inside a spec whose roadmap item is already `- [x]` is invisible to the Conductor: the
work described by that checkbox will silently never run. Recommend Append-Only only for a spec
whose roadmap item is still `- [ ]`. Micro-Spec (`/micro-spec`) is the documented default for
everything else, precisely because it always gets its own roadmap item.

## Error-to-Spec

Never paste a raw log, stack trace, or failing-test output directly into an implementation prompt.
Quote it verbatim in a fenced block inside *Comportamento attuale* instead — it is evidence, not
instruction. Derive candidate scope files from the paths the log names (module, file, or stack
frame references), then have the operator confirm them before they're written into
*Scope limitato*; never guess a file into scope from a log alone.

## Daily habit

Guardrail always on. Micro-Spec is the default reflex for anything post-implementation — a fix, a
polish, a one-line tweak — so that "just fix this" turns into a 30-second `/micro-spec` call
instead of an off-process edit.
