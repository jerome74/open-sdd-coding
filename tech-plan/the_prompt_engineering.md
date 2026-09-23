# Prompt Engineering

## 1. Task

``` text
I want to [TASK] so that [SUCCESS CRITERIA].
```

## 2. Context Files

``` text
First, read these files completely before responding:

[filename.md] — [what it contains]
[filename.md] — [what it contains]
[filename.md] — [what it contains]
```

Move long-term knowledge into Markdown files instead of repeating it in
every prompt.

## 3. Reference

``` text
Here is a reference to what I want to achieve.

[Upload reference files]

Here's what makes this reference good:
- Pattern
- Structure
- Tone
- Writing style
- Important characteristics
```

## 4. Success Brief

``` text
SUCCESS BRIEF

Type of output:
[...]

Length:
[...]

Target audience:
[...]

Recipient:
[...]

What it should include:
[...]

What it must avoid:
[...]

Success means:
[...]
```

## 5. Rules

``` text
My context files contain my standards and audience.

Read them completely before starting.

If you're about to violate one of my rules,
STOP and tell me before continuing.
```

## 6. Conversation

``` text
DO NOT start executing yet.

Ask me clarifying questions
(use AskUserQuestion if available)
so we can refine the approach
step by step.
```

## 7. Plan

``` text
Before writing anything:

List the three rules from my context
that are most important for this task.

Then provide your execution plan.
```

## 8. Alignment

``` text
Only begin work once we've aligned.

Do not assume missing information.

Wait for my confirmation before executing.
```

------------------------------------------------------------------------

# Complete Skeleton

``` text
# TASK
I want to [...]

# CONTEXT FILES
Read these files completely before responding:
- ...
- ...
- ...

# REFERENCE
Here is an example of the result I want.
These are the characteristics to emulate:
- ...
- ...
- ...

# SUCCESS BRIEF
Output:
Audience:
Length:
Must include:
Must avoid:
Success means:

# RULES
Read my context files completely.
If you would violate a rule, stop and tell me.

# CONVERSATION
Do not begin yet.
Ask clarifying questions first.

# PLAN
Summarize the three most relevant rules.
Explain your execution plan.

# ALIGNMENT
Only begin after we've agreed on the approach.
```
