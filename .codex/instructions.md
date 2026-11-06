# Codex runtime adapter

Root AGENTS.md remains shared and unmodified. Its SDD, language, citation and raw immutability
rules apply. This file translates OpenCode runtime notation only; it does not waive workflow gates.

- OpenCode /command becomes a Codex skill invocation. The catalog maps names, including
  $sdd-implement and $sdd-prompt-engineering. $plan is a workflow skill, distinct from Codex /plan.
  Treat explicit workflow skill invocations as commands for sdd-guardrail; plain chat remains plain chat.
- Read a skill's SKILL.md to load it. There is no OpenCode skill() tool or Task tool in Codex.
  Use native subagent tools only for the delegations authorized by the active workflow.
  Child agents never spawn agents. The SDD Conductor always stays in the primary thread.
- Discover roles from .codex/agents/*.toml (name, description); discover capabilities from
  .agents/skills/*/SKILL.md (name, description). These are the Codex registry roots, not guesses
  from filenames. Read .codex/capability-registry.md for the inventory and permission caveats.
  Workflow entrypoints are reference commands, never artifact producers bound by SDD discovery.
- Source script paths under .opencode/skills remain executable shared resources. Read them as
  needed, never edit them from a migrated workflow. Missing artifacts and optional dependencies
  remain explicit gaps. docs/graphrag.md and the SDD constitution are absent in the baseline;
  do not fabricate them or project state to pass a prerequisite.
- Custom native agents inherit the parent's permissions in Codex 0.166.0. The read-only roles
  planner, sdd-governor and knowledge-searcher must NOT be spawned in a writable parent session.
  Use their embedded read-only workflow fallback, or an isolated read-only session through
  scripts/codex_workflow.py agent <name> --run with the relevant context. Native spawn is allowed
  when the parent itself is read-only. Supply artifact text when the role has no shell tools.
  Read-only isolation is stronger than a prompt; never claim a role TOML creates a sandbox.
- micro-spec-author has no shell tools and its two-file write scope is behavioral, as in the
  source definition. Supply file contents from the parent and review the returned patch scope.
- Root permissions protect raw and .opencode from all writes, including shell writes; this is
  intentionally stricter than source append-only raw. Do not escalate or disable the sandbox to
  bypass those paths. New versions of sources require a separate user-authorized ingestion.
- git push requires approval. OpenCode rm -rf denial is retained by execpolicy; no policy
  bypass, automatic approval or external publication is authorized by migration itself.
- Models/provider/auth are inherited from the operator's Codex installation; OpenCode agents no longer
  pin a model either. Knowledge-pipeline extraction (/generate-llm-wiki Phase 1, `$generate-llm-wiki`)
  runs in the primary thread through the `graphify` skill with the session model: no provider API key,
  no `graphify extract --backend`, staged via `GRAPHIFY_OUT=<stage_dir>/<slug>`.
  Do not add providers, connect disabled MCP servers, install models or perform API smoke tests
  without explicit authorization. MCP definitions remain disabled; optional cloud examples in
  shared skills do not authorize any connection.
- Agent editing restrictions that lack a native per-tool equivalent remain binding behavior;
  report limitations, never claim edit/write/bash permissions were mechanically preserved.
  Native registered roles and isolated adapter sessions are different execution modes.
- Original workflow prompts can contain OpenCode-specific comments about permissions or plugins.
  Apply Codex permissions and this adapter, never treat opencode.json as Codex enforcement.
  RTK uses a separate optional Codex hook, subject to native hook trust; DCP/cache plugins are
  not loaded by Codex. There is no installed TypeScript plugin bridge.
- Before source-changing workflows, preserve the source's user confirmation, planning,
  governance, overwrite and publication gates. Missing constitution: report bootstrap, never
  invent a roadmap. Compact/new session between roadmap items, then reread Roadmap.
