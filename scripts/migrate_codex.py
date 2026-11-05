#!/usr/bin/env python3
"""Generate additive Codex adapters without changing OpenCode originals (stdlib only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = {
    'SDD-implement': 'sdd-implement', 'gather-requirements': 'gather-requirements',
    'generate-llm-wiki': 'generate-llm-wiki', 'init-new-project': 'init-new-project',
    'micro-spec': 'micro-spec', 'plan': 'plan', 'prompt-engineering': 'sdd-prompt-engineering',
    'publish-llm-wiki': 'publish-llm-wiki', 'spec-brainstorm': 'spec-brainstorm',
}
READ_ONLY = {'planner', 'sdd-governor', 'knowledge-searcher'}
NO_SHELL = {'planner', 'sdd-governor', 'micro-spec-author'}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_snapshot(root: Path) -> dict:
    files, links = {}, {}
    for path in sorted((root / '.opencode').rglob('*')):
        if path.is_symlink():
            links[path.relative_to(root).as_posix()] = str(path.readlink())
        elif path.is_file():
            files[path.relative_to(root).as_posix()] = sha(path)
    for name in ('opencode.json', 'AGENTS.md', 'knowledge-config.json'):
        files[name] = sha(root / name)
    return {'files': files, 'symlinks': links}


def split_source(path: Path) -> tuple[dict, str]:
    """Read the simple metadata used by this project, including its invalid plain YAML description.

    This is intentionally not a general YAML parser. Codex validates generated skill YAML.
    """
    text = path.read_text(encoding='utf-8')
    if not text.startswith('---\n'):
        raise ValueError(f'{path}: missing frontmatter')
    _, front, body = text.split('---', 2)
    values = {}
    lines = front.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r'^([\w-]+):\s*(.*)$', line)
        if not match:
            continue
        key, value = match.groups()
        if value in ('>', '>-', '|', '|-'):
            continuation = []
            for following in lines[index + 1:]:
                if following and not following.startswith(' '):
                    break
                continuation.append(following.strip())
            value = ' '.join(continuation).strip()
        elif value.startswith('"') and value.endswith('"'):
            value = json.loads(value)
        values[key] = value
    if not values.get('description'):
        raise ValueError(f'{path}: description required')
    return values, body.lstrip('\n')


def convert(body: str) -> str:
    """Translate executable conventions; keep source scripts/resources at their original paths."""
    body = re.sub(r'skill\(\{\s*name:\s*"([^"]+)"\s*\}\)',
                  lambda m: f'read .agents/skills/{m[1]}/SKILL.md', body)
    body = body.replace('$ARGUMENTS', 'workflow_arguments').replace('$1', 'workflow_arg1')
    for source, target in COMMANDS.items():
        body = re.sub(r'(?<![\w./-])/' + re.escape(source) + r'\b', '$' + target, body)
    body = re.sub(r'@([a-z][a-z-]+)', r'\1', body)
    body = body.replace('.opencode/agents/*.md', '.codex/agents/*.toml')
    body = re.sub(r'\.opencode/agents/([\w-]+)\.md', r'.codex/agents/\1.toml', body)
    body = body.replace('.opencode/commands/*.md', '.agents/skills/*/SKILL.md (workflow entrypoints)')
    body = body.replace('.opencode/skills/*/SKILL.md', '.agents/skills/*/SKILL.md')
    body = body.replace('docs/sdd/capability-registry.md', '.codex/capability-registry.md')
    body = body.replace('via Task', 'via native Codex subagent tools')
    body = body.replace('Task-tool call', 'Native Codex subagent call').replace('Task tool', 'native Codex subagent tools')
    body = body.replace('(`skill(', '(`read the skill file (')
    body = body.replace('deepseek/deepseek-flash', 'the operator-selected Codex model')
    body = body.replace('from `/models`', 'from the operator’s Codex model selector')
    body = body.replace('a DeepSeek model', 'an available Codex model')
    body = body.replace('opencode.json` (config)', '.codex/config.toml` (config)')
    body = body.replace('`opencode.json` (config)', '`.codex/config.toml` (config)')
    body = body.replace('Tooling grants only read/search, so authoring is impossible by construction.', 'The role permits only read/search; use a read-only parent or isolated adapter for runtime enforcement.')
    # Original links live two levels below repo; generated workflow skills live three below it.
    body = body.replace('](../../docs/', '](../../../docs/')
    return body


INSTRUCTIONS = '''# Codex runtime adapter

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
- Models/provider/auth are inherited from the operator's Codex installation. DeepSeek model IDs,
  temperatures, context limits and cache flags are not transplanted. OpenCode keeps its backend.
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
'''

CONFIG = '''# Codex CLI 0.166.0; OpenCode configuration remains independent.
# No model/provider/auth override: use the operator's existing Codex installation.
approval_policy = "on-request"
default_permissions = "sdd"
developer_instructions = "Before using migrated workflows, read .codex/instructions.md. Root AGENTS.md remains binding; adapt only OpenCode runtime notation. Native read-only roles must not be spawned from writable sessions; use the embedded fallback or the read-only adapter."

[agents]
enabled = true
max_concurrent_threads_per_session = 4

[features]
apps = false
plugins = false

[permissions.sdd]
extends = ":workspace"
description = "SDD workspace; immutable sources and original OpenCode are read-only"

[permissions.sdd.filesystem.":workspace_roots"]
"raw" = "read"
".opencode" = "read"

[permissions.sdd.network]
enabled = false

[mcp_servers.tavily]
command = "npx"
args = ["-y", "tavily-mcp"]
enabled = false

[mcp_servers.fetch]
command = "uvx"
args = ["mcp-server-fetch"]
enabled = false

[mcp_servers.docs]
command = "npx"
args = ["-y", "@upstash/context7-mcp"]
enabled = false

[mcp_servers.github]
url = "https://api.githubcopilot.com/mcp/"
bearer_token_env_var = "GITHUB_TOKEN"
enabled = false

[[hooks.PreToolUse]]
matcher = "^Bash$"

[[hooks.PreToolUse.hooks]]
type = "command"
command = 'python3 "$(git rev-parse --show-toplevel)/scripts/codex_rtk_hook.py"'
timeout = 5
'''

RULES = '''# Prefix-based guardrails; not a universal shell-program analyzer.
prefix_rule(pattern = ["git", "push"], decision = "prompt")
prefix_rule(pattern = ["rm", ["-rf", "-fr"]], decision = "forbidden")
'''


def artifact_hash(path: Path) -> str:
    return 'link:' + str(path.readlink()) if path.is_symlink() else sha(path)


def generate(root: Path = ROOT) -> dict:
    root = root.resolve()
    manifest_path = root / '.codex/migration-manifest.json'
    prior = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    snapshot = source_snapshot(root)
    outputs: dict[str, str] = {}
    symlinks: dict[str, str] = {}
    rows = []
    for folder in sorted((root / '.opencode/skills').iterdir()):
        if not folder.is_dir() or not (folder / 'SKILL.md').is_file():
            continue
        meta, body = split_source(folder / 'SKILL.md')
        name = meta['name']
        destination = '.agents/skills/' + name
        if name == 'wiki-semantic-search':
            outputs[destination + '/SKILL.md'] = ('---\nname: ' + name + '\ndescription: ' + json.dumps(meta['description']) + '\n---\n\n' + body)
            symlinks[destination + '/scripts'] = '../../../.opencode/skills/' + name + '/scripts'
            strategy, compatibility = 'YAML adapter; scripts symlink', 'parziale (YAML originale invalido)'
        else:
            symlinks[destination] = '../../.opencode/skills/' + folder.name
            strategy, compatibility = 'symlink', 'equivalente; dipendenze originali'
        rows.append(dict(source=folder.relative_to(root).as_posix(), kind='skill', target=destination,
                         name=name, description=meta['description'], strategy=strategy, compatibility=compatibility))
    command_sources = sorted((root / '.opencode/commands').glob('*.md'))
    if {x.stem for x in command_sources} != set(COMMANDS):
        raise ValueError('command inventory changed: classify new commands before conversion')
    agent_sources = sorted((root / '.opencode/agents').glob('*.md'))
    for path in command_sources:
        meta, body = split_source(path)
        name = COMMANDS[path.stem]
        prefix = f'''# Codex invocation contract

Invoke as `${name} <arguments>`. This is a primary-thread workflow, not a delegable agent.
Read `.codex/instructions.md` before executing it. Source: `{path.relative_to(root)}`.
`workflow_arguments` means the exact text after this skill mention; `workflow_arg1` means
its first positional argument. For the CLI adapter use the JSON `workflow_input.arguments`
array and its `raw` field, never re-evaluate arguments as shell code. Missing input keeps the
source workflow's question/default behavior. Skill loading performs no shell substitution.
A native `/plan` or `/init-new-project` command is not assumed to exist. Preserve every
source confirmation gate; this migration does not authorize remote effects.

'''
        converted = convert(body)
        converted = re.sub(r'> Model: frontmatter pins.*?(?=\n\n)', '> Model: inherit the operator-selected Codex model; no per-workflow pin or automatic substitution.', converted, flags=re.S)
        if path.stem == 'plan':
            converted = converted.replace('## Input / Output', '''## Read-only delegation on Codex

The planner's role stays separate from the primary writer. Native planner delegation is
allowed only in a read-only parent session. From a writable parent use the isolated
read-only role adapter, or apply its definition as a distinct `Planning checkpoint (embedded)`
that drafts only in the reply. Preserve the explicit user confirmation before the primary
writes the engineering plan. Never treat the role TOML as a private read-only sandbox.

## Input / Output''')
        if path.stem == 'SDD-implement':
            start = converted.index('### Phase 0 — Discover capabilities')
            end = converted.index('### Phase 1 — Resolve input', start)
            converted = converted[:start] + '''### Phase 0 — Discover capabilities

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

''' + converted[end:]
        if path.stem == 'generate-llm-wiki':
            a = converted.index('**Immutable-root sweep.**')
            b = converted.index('If the bundle changed this run', a)
            converted = converted[:a] + '''**Immutable-root inspection.** After the agent returns, inspect configured immutable
roots read-only for stray `graphify-out` directories. If found, report the exact paths and
stop; do not delete anything inside an immutable root. Root AGENTS.md forbids such cleanup.

''' + converted[b:]
        outputs[f'.agents/skills/{name}/SKILL.md'] = ('---\nname: ' + name + '\ndescription: '
            + json.dumps(meta['description']) + '\nmetadata:\n  workflow-entrypoint: "true"\n---\n\n' + prefix + converted)
        rows.append(dict(source=path.relative_to(root).as_posix(), kind='command', name=name, description=meta['description'],
                         target=f'.agents/skills/{name}/SKILL.md', strategy='workflow skill + argv adapter',
                         compatibility='parziale (invocazione e tool adattati)'))
    for path in agent_sources:
        meta, body = split_source(path)
        name = path.stem
        preface = ('Codex runtime: read .codex/instructions.md. Never spawn subagents. '
                   'Use only the model/provider configured by the operator. '
                   'Load skills by reading their SKILL.md; there is no OpenCode Task or skill tool.\n')
        if name in READ_ONLY:
            preface += ('READ-ONLY: native roles inherit parent permissions. If the parent can write, '
                        'perform no tools and return REQUEST_READ_ONLY_ADAPTER to the parent. '
                        'Use only a read-only parent or the isolated adapter; never request write escalation.\n')
        converted = convert(body)
        converted = re.sub(r'> \*\*Model note\.\*\*.*?(?=\n\n)', '> **Model note.** Inherit the operator-selected Codex model; no automatic substitution.', converted, flags=re.S)
        data = dict(name=name, description=meta['description'], developer_instructions=preface + '\n' + converted)
        outputs[f'.codex/agents/{name}.toml'] = '\n'.join(key + ' = ' + json.dumps(value, ensure_ascii=False) for key, value in data.items()) + '\n\n[features]\napps = false\nplugins = false\n' + ('shell_tool = false\n' if name in NO_SHELL else '')
        rows.append(dict(source=path.relative_to(root).as_posix(), kind='agent', name=name, description=meta['description'],
                         target=f'.codex/agents/{name}.toml', strategy='native standalone TOML + session adapter',
                         compatibility='parziale (permessi e modello)'))
    # Independently authored Codex skills are registered, never generated or overwritten.
    local_root = root / '.agents/skills'
    known_names = {row['name'] for row in rows}
    if local_root.is_dir():
        for folder in sorted(local_root.iterdir()):
            entry = folder / 'SKILL.md'
            if not entry.is_file():
                continue
            meta, _ = split_source(entry)
            if meta['name'] in known_names:
                continue
            rows.append(dict(source=folder.relative_to(root).as_posix(), kind='skill', name=meta['name'],
                             description=meta['description'], target=folder.relative_to(root).as_posix(),
                             strategy='independent Codex skill; preserve original files', compatibility='nativa'))
            known_names.add(meta['name'])
    outputs['.codex/config.toml'] = CONFIG
    outputs['.codex/instructions.md'] = INSTRUCTIONS
    outputs['.codex/rules/sdd.rules'] = RULES
    registry = ['# Codex Capability Registry', '', 'Inventory by metadata, no SDD progress state.',
                'OpenCode keeps its original discovery roots and registry fallback.', '',
                '| Kind | Name | Native artifact | Source | Declared purpose |', '|---|---|---|---|---|']
    for row in rows:
        registry.append(f"| {row['kind']} | {row['name']} | `{row['target']}` | `{row['source']}` | {row['description'].replace('|', '/')} |")
    registry += ['', 'Models inherit the operator-selected Codex session. DeepSeek and temperatures are not mapped.',
                 'Read-only roles require read-only parents or the isolated session adapter. Role TOML does not create a sandbox.',
                 'Workflow entrypoints carry metadata.workflow-entrypoint=true and never bind as artifact producers.',
                 'Skill wiki-semantic-search uses a YAML adapter. GraphRAG documentation links are absent upstream; report the gap.',
                 'After adding/renaming source assets, regenerate and review the inventory; never infer a role from its filename.']
    outputs['.codex/capability-registry.md'] = '\n'.join(registry) + '\n'
    # Preflight all writes. Do not overwrite pre-existing or locally edited Codex assets.
    for name in [*outputs, *symlinks, '.codex/migration-manifest.json']:
        path = root / name
        for parent in path.parents:
            if parent == root:
                break
            if parent.is_symlink():
                raise ValueError(f'preserve existing symlinked parent: {parent.relative_to(root)}')

    for name, content in outputs.items():
        path = root / name
        if path.exists() or path.is_symlink():
            expected = hashlib.sha256(content.encode()).hexdigest()
            if artifact_hash(path) not in (expected, prior.get('outputs', {}).get(name)):
                raise ValueError(f'preserve existing Codex artifact: {name}')
    for name, target in symlinks.items():
        path = root / name
        if path.exists() or path.is_symlink():
            if not path.is_symlink() or str(path.readlink()) != target:
                raise ValueError(f'preserve existing skill/path: {name}')
    for name, content in outputs.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_text(encoding='utf-8') != content:
            path.write_text(content, encoding='utf-8')
    for name, target in symlinks.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_symlink():
            path.symlink_to(target, target_is_directory=True)
        if not path.is_dir():
            raise ValueError(f'broken symlink: {name} -> {target}')
    if source_snapshot(root) != snapshot:
        raise ValueError('OpenCode originals changed during migration')
    manifest = dict(schema_version=1, tested_codex_version='0.166.0', sources=snapshot,
                    inventory=rows, outputs={name: artifact_hash(root / name) for name in [*outputs, *symlinks]})
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='check source integrity and generated outputs without writing')
    args = parser.parse_args()
    try:
        if args.check:
            manifest = json.loads((ROOT / '.codex/migration-manifest.json').read_text())
            if source_snapshot(ROOT) != manifest['sources']:
                raise ValueError('source snapshot changed; review before regeneration')
            for name, expected in manifest['outputs'].items():
                if artifact_hash(ROOT / name) != expected:
                    raise ValueError(f'generated artifact changed: {name}')
        else:
            manifest = generate()
        print(json.dumps({'status': 'ok', 'artifacts': len(manifest['inventory']), 'outputs': len(manifest['outputs'])}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
