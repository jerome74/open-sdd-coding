---
name: prompt-engineering
description: "Fill the Prompt Engineering template (tech-plan/the_prompt_engineering.md) from a user's raw, free-form ask, grounding every filled field only in what the user explicitly said or confirmed — never silently inferring or completing missing parts. Use when structuring a free-form ask into that framework, when asked to 'compile the prompt engineering template', or when the /prompt-engineering command runs."
---

# Prompt Engineering — grounded compilation

## Structural source of truth

Read `tech-plan/the_prompt_engineering.md` in full at the start of every invocation. Do not
hardcode a copy of its section structure here — if that file changes, this skill must follow it
without needing an edit. The "Complete Skeleton" at the bottom of that file is the shape of the
document you assemble; the numbered sections above it (1-8) explain what belongs in each part.

## Two kinds of section

- **Sections 1-4 (Task, Context Files, Reference, Success Brief) are variable content.** Every
  word you put there must be traceable to something the user actually said or confirmed. This is
  where the no-fabrication rule below applies.
- **Sections 5-8 (Rules, Conversation, Plan, Alignment) are fixed scaffolding.** Their text in the
  "Complete Skeleton" is constant regardless of what the user asked for — reproduce it near
  verbatim. The only adaptation allowed: if Section 2 ends up empty (no context files at all),
  adjust the opening of Section 5 so it does not refer to "your context files" when there are
  none. Do not otherwise personalize sections 5-8 — they are the standing discipline that governs
  how you behave once the document is assembled (see "After assembling the document" below).

## Grounding rule and escalation ladder (sections 1-4 only)

Never invent a conclusion for a field the user did not cover. When a field in Sections 1-4 (or a
sub-field, e.g. one row of the Success Brief, or a file description in Section 2/3) has no
grounded content, escalate through these steps in order — do not skip to the end:

1. **Ask the user directly**, one question at a time, whether they want to provide that piece of
   information.
2. **If they don't have it or decline**: ask whether you should try to derive it by re-reading
   what they have already written elsewhere in this exchange — inference over their own words,
   never invention of new facts not traceable to anything they said.
3. **If that still yields nothing** (they decline step 2, or the re-read finds nothing grounded):
   mark that field with an explicit statement that it is absent (e.g. "Not covered — no
   information provided or derivable"). Never leave a bare, ambiguous placeholder without having
   gone through steps 1-2 first.

Apply this same ladder to the Section 3 "what makes this reference good" bullets (Pattern,
Structure, Tone, Writing style, Important characteristics) — fill only what the user stated
explicitly; run the ladder on the rest rather than guessing plausible bullets.

## Attachments — Context Files vs Reference

When the user offers or is asked about a file, classify it with one question at a time that always
states the difference, not just the two labels:

- **Context Files (Section 2)** = background/supporting knowledge you should read before
  responding — standards, policy, domain documentation, reference data.
- **Reference (Section 3)** = an example of the desired output — something to imitate for pattern,
  structure, tone, or style, not background knowledge.

If a file is already referenced by path in the user's own raw ask (not offered as an attachment,
just mentioned), treat it as already classified for whichever section that mention implies, but
still ask if there is anything else to attach.

## Conversion to Markdown

If the chosen file is not already `.md`, convert it before listing it:

- For formats `pandoc` handles directly (`.docx`, `.odt`, `.rtf`, `.html`, `.epub`): run
  `pandoc <file> -t gfm -o <file-without-ext>.md`.
- For formats `pandoc` handles poorly (PDF, images, plain text, code), **or when `pandoc` is not
  installed**: read the file directly and transcribe it faithfully into Markdown — do not
  summarize, paraphrase away detail, or drop content.
- Always write the conversion as `<same-name>.md` next to the original file. Never overwrite or
  delete the original.
- Section 2 (and Section 3, when applicable) must reference the resulting `.md` path — never the
  original non-Markdown file.

## Output filename

The assembled document is saved under `engineering/prompt/`, the same directory `/plan` reads
from. Derive a short kebab-case slug from Section 1 (Task) — e.g. a task about "real-time market
resolution notifications" becomes `realtime-notifications.md`. If no clear slug can be derived,
ask the user for one; never guess a name unrelated to the stated Task.

## After assembling the document

Once Sections 1-8 are filled (or explicitly marked absent per the escalation ladder), write the
compiled document to `engineering/prompt/<slug>.md` and treat it as the operating prompt for the
rest of the exchange. Its own Section 6 requires asking clarifying questions before starting,
Section 7 requires summarizing the most relevant rules and giving an execution plan, and Section 8
requires waiting for explicit alignment before execution — follow that discipline against the
document you just produced instead of re-inventing a separate process.
