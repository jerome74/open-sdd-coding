# Rollback policy and trust boundary

## Attribution

A clean Git commit is not required. The initial scope is captured, hashed and persisted BEFORE
execution. The private workspace contains only copies of those input files. The executor's cwd
is that workspace. The publisher compares its output against the initial snapshot and applies
only that delta to the real repository. Actual host edits during execution are never simply
assigned to the skill: a forward three-way merge preserves disjoint edits, or publication fails.
Each changed file stores initial, produced, effective-before-publication and published-after states.
The inverse uses the latter pair, so pre-existing and concurrent manual edits remain intact.

The skill name is an explicit caller declaration checked against installed repository skills;
the manifest records the executor hash and publisher provenance, not proof of an LLM's internal
reasoning. No implicit skill lifecycle hook is assumed. `prepare`/`finish` and `run` are the only
trusted entrypoints. Never manufacture a retrospective run for a direct or interrupted old skill.

The workspace is private (0700) and the repository-wide tracking lock serializes cooperating
publishers. This is not an OS sandbox or protection against malicious same-user processes.
Commands must keep all output in declared scopes, complete all child writers, and use explicit
read-only input paths for other resources. Arbitrary absolute writes, remote effects, Git writes,
and background processes are outside the rollback contract. Use the native Codex workspace
sandbox without escalation for model-driven work. If that cannot be done, refuse automatic
tracking of the broader workflow. Never assert exhaustive attribution for an unrestricted tool.

## Files and conflicts

- All output scopes must be explicit relative file/directory paths; dot, parent traversal,
  absolute paths, NUL, symlinks, hardlinks and nonregular files are rejected.
- Protected root raw; protected components .git, .opencode, .agents, .codex, node_modules, .ssh, .aws and tracking
  storage. Credential names, .env* and private-key/container extensions are blocked by default.
  This is a filename policy, not a secret-content detector.
- Modified files: exact after-state → restore before-state. Otherwise use a conservative UTF-8
  three-way line merge with after as base, current as ours and before as desired. Touching or
  overlapping edit regions conflict; never emit conflict markers or silently choose one side.
- Created files: remove only if unchanged. Already absent → no-op. Later changes → conflict.
  Later active tracked runs that copied the created path block removal even if they did not
  modify it. Explicit `--depends-on` blocks inverse of its upstream run. Unknown semantic
  dependencies, including manual cross-file references, require user review: this is not a
  semantic dependency analyzer. Do not apply when the user identifies such an ambiguity.
- Deleted files: restore only to absent paths; an identical already-restored file needs no write.
  A path reused with different contents, directory, or symlink conflicts.
- Rename: only an explicit `--rename OLD NEW` declaration verified as an exact content/mode
  move is recorded as a rename. Other delete/create pairs stay separate; modified renames need
  separate review. The transaction reverses the two file operations together via its journal.
- Binary or non-UTF-8 content: snapshots only; unequal later content conflicts. Permission-only
  changes are tracked. Unrelated later file mode changes are preserved when separable.
- No partial application of a plan with known conflicts. All files and blobs preflight before
  the checkpoint. `--force` never weakens any check.

## Transactions and recovery

Each working-tree file replacement is atomic via a temporary sibling and replace. Deletions use
unlink of one verified path, never recursive deletion. Parent directory traversal uses POSIX
O_NOFOLLOW/dir_fd; the tracker also refuses symlink paths when planning. File bytes/modes are
rechecked immediately before writes. Locks do not freeze external editors; there is no
multi-file filesystem transaction or universal compare-and-swap guarantee against hostile races.

Before writes, the run manifest persists a checkpoint of EVERY current target state and a
write-ahead operation journal. On failure it stays needs_recovery. Other tracked operations
refuse unfinished runs. Recovery preflights all targets against the checkpoint/desired states,
then compensates in reverse order. If anything changed externally after the failure it stops
without overwriting it. Recovery itself is resumable and repeatable using the same journal.
Empty directories can remain; directory metadata, ACLs, xattrs, ownership and special files are
not tracked. Explicit abandon only closes a prepared, unpublished run, never an applying journal.

## Persistence and Git

Storage is `.rollback-state/` rather than `.codex/rollback-state/`: the Codex config directory
is protected against writes during ordinary sessions. The state root and subdirectories require
0700; blobs/manifests/logs are 0600. Add the state root to .gitignore before preparing runs; already versioned or nonignored storage is refused. Snapshots may contain
sensitive content despite filename exclusions; do not publish, copy into knowledge input roots,
or include them in prompts. Logs contain IDs, paths, operation metadata and hashes, never argv,
stdout or file contents. Manifest hashes detect corruption, not malicious authorized rewriting.

No reset, clean, checkout, revert, commit or push is used. Git rev-parse reads initial/current commit IDs; check-ignore and ls-files verify that
tracking storage is ignored and not versioned; working-tree operations preserve Git's index. Later commits are allowed and remain
unchanged; rollback can leave the working tree different from committed/index content.

Retention is indefinite, without automatic deletion; blobs are content-addressed and reused.
Default snapshot budget is 100 MiB per input/output scope capture and can be set with --max-bytes.
Checkpoint, workspace and retained output can consume multiples of that budget across runs.
`tracking.py status` reports storage usage. Review and archive/move the ENTIRE private state
store after all unfinished journals are resolved; removing the store loses rollback history.
Never delete individual shared blobs or a live lock file. No pruning is performed automatically.

## Exit codes

rollback.py: 0 = preview, cancellation, applied or already-applied; 2 = conflict/invalid/untracked;
3 = confirmation required in non-TTY; 130 = interrupted (inspect recovery state).
tracking.py: 0 = success; 2 = failure or invalid input. Argument errors use argparse diagnostics.
Only POSIX platforms with flock, dir_fd, O_NOFOLLOW and directory fsync are supported by v1.
