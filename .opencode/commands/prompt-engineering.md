---
description: "Structure a raw, free-form ask into the Prompt Engineering framework (tech-plan/the_prompt_engineering.md), grounded only in what the user actually said, then execute it"
argument-hint: "(optional) your raw, unstructured ask — or leave empty for a guided, section-by-section interview"
---

# Prompt Engineering

Turn a free-form ask into the Prompt Engineering framework, then use the compiled document as the
operating prompt for the rest of this session. Load and apply the `prompt-engineering` skill
throughout (`skill({ name: "prompt-engineering" })`): it holds the grounding rule, the escalation
ladder for ungrounded fields, the Context-vs-Reference attachment flow, and the conversion
procedure. This command does not duplicate those rules — it only sequences them.

> This is an auxiliary engineering-workflow command, not part of the five-command SDD pipeline.

## Process

### 1. Capture

- If `$ARGUMENTS` is not empty: treat it as the raw ask. Extract grounded content for Sections
  1-4 (Task, Context Files, Reference, Success Brief) from it.
- If `$ARGUMENTS` is empty: run a **guided, section-by-section interview** instead of asking the
  user to paste a raw prompt. Ask about Task, then Context Files, then Reference, then Success
  Brief, one section at a time. Every question always opens with a very short description (max 20
  words) of the section you're about to fill, so the user knows what's being asked and why before
  answering. Rework each answer into better-structured content before placing it in that section
  — do not transcribe it verbatim.
- In both cases, for any field left uncovered, run the escalation ladder from the
  `prompt-engineering` skill (ask → try to derive from what's already been said → mark explicitly
  absent). Never default straight to a placeholder.

### 2. Attachments

Ask once whether the user wants to attach any files. If yes, for each file: ask which section it
belongs to, stating the Context-vs-Reference difference in the question itself (per the skill).
Convert non-Markdown attachments per the skill's conversion procedure, writing the `.md` copy
beside the original. Update Section 2 or 3 accordingly. Repeat until the user says they're done.

### 3. Assemble and save

Compile the fully assembled document — Sections 1-8, in the "Complete Skeleton" shape from
`tech-plan/the_prompt_engineering.md` — and present it in the conversation. Derive a short
kebab-case slug from Section 1 (Task), per the skill's "Output filename" rule, and write the
document to `engineering/prompt/<slug>.md`. Confirm the saved path to the user.

### 4. Hand off to execution

From here, follow the compiled document as your own operating prompt:

1. Apply its Section 6 — ask any remaining clarifying questions before doing anything else.
2. Apply its Section 7 — summarize the three most relevant rules from Section 5 and give an
   execution plan.
3. Apply its Section 8 — wait for the user's explicit confirmation that you're aligned.

Only after that confirmation, execute the Task described in Section 1. Mention that
`/plan <slug>.md` can also be run against the saved file to produce a step-by-step implementation
plan.
