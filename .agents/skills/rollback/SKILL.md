---
name: rollback
description: Selectively undo the latest or a specified genuinely tracked skill run, previewing changes and preserving later edits. Use for explicit rollback requests, dry runs, and recovery of interrupted tracked transactions. Refuse automatic rollback of untracked executions; never use repository-wide reset, clean, or commit reverts.
---

# Rollback a tracked skill run

This skill uses the deterministic scripts below, not chat history or a guess from git status.
Read [rollback-policy.md](references/rollback-policy.md) before applying a rollback or recovery.
Only executions prepared BEFORE running in the private tracking workspace can be reversed.
Direct `$other-skill` invocations and earlier sessions are not automatically tracked.

## Arguments and preview

Transfer the exact positional skill name and each flag as separate subprocess arguments.
Do not use eval, shell substitution, or reinterpret file paths as commands. The Python script
uses argparse; unknown flags are errors. Supported invocation:

```text
$rollback <skill-name>
$rollback <skill-name> --dry-run
$rollback <skill-name> --run-id <id>
$rollback <skill-name> --force
```

From the repository root, first run:

```bash
python3 -B .agents/skills/rollback/scripts/rollback.py <skill-name> --dry-run
```

Include `--run-id <id>` when supplied. Inspect status, run ID, operations, merged flags,
conflicts and plan_hash. `--dry-run` performs no writes, including tracking/log writes.
No run or incomplete attribution: report the error and stop. Do not reconstruct prior state
from Git, timestamps, filename similarity, conversation text, or an untracked manifest.

## Confirmation and apply

For standard invocation, present the exact preview and ask the user for confirmation. In a
non-TTY agent shell the script returns `confirmation_required` (exit 3); this is not approval.
After explicit confirmation, pass the exact run ID and preview hash:

```bash
python3 -B .agents/skills/rollback/scripts/rollback.py <skill-name> --run-id <id> --plan-hash <hash> --force
```

Here `--force` only bridges the user's confirmation to the noninteractive script. If the user
explicitly requested `$rollback ... --force`, no additional confirmation is needed: preview
and apply with the same checks. Conflicts, missing/corrupt snapshots, unsafe paths, dependencies,
concurrency and incomplete runs still block. Never escalate filesystem permissions to bypass a
protected root or repair a conflict automatically. A changed plan requires a new review.

Already-applied rollback: report no-op; never select an older run automatically. Multiple files
are recoverable but not atomically switched as one operation. On interruption or failure,
inspect `tracking.py status`; if a transaction is applying, report `recovery_required`.

## Make future runs traceable

The central wrapper prepares snapshots before the command, runs it in a private workspace,
and publishes only declared output scopes, preserving concurrent host edits or refusing conflicts:

```bash
python3 -B .agents/skills/rollback/scripts/tracking.py run <installed-skill-name> --path src --path generated -- <command> <arg> ...
```

The command must operate inside its supplied cwd and exit after all writers finish. Pass program
paths explicitly if needed; dependencies and project context are not copied automatically.
For model-driven tasks use `prepare`, run the skill in the returned workspace using Codex's
workspace sandbox without escalation, then `finish <run-id>`. Read policy for the exact contract.
The wrapper is NOT an OS sandbox for arbitrary subprocesses: external effects, absolute writes,
Git history/index operations, cloud actions and background daemons are not reversible. Refuse
this tracking route if a workflow cannot honor that boundary. Do not claim its entire normal
execution was tracked merely because some outputs were published by this wrapper.

## Recovery

```bash
python3 -B .agents/skills/rollback/scripts/tracking.py --repo <repo> status
python3 -B .agents/skills/rollback/scripts/tracking.py --repo <repo> recover <run-id>
```

Review the stored checkpoint/journal and request approval for recovery before running it.
Recovery restores the checkpoint of the interrupted transaction only if all current paths still
match its known before/after states; otherwise it refuses. Do not delete locks or edit manifests.
Never touch raw, original OpenCode assets, credentials, Git metadata or paths outside the repo.
