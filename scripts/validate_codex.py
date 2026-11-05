#!/usr/bin/env python3
"""Validate the migration and optionally probe Codex locally without any turn/start."""
from __future__ import annotations

import argparse
import json
import queue
import re
import subprocess
import sys
import tempfile
import threading
import tomllib
from pathlib import Path

sys.dont_write_bytecode = True
from migrate_codex import COMMANDS, ROOT, artifact_hash, source_snapshot  # noqa: E402


def static_check(root: Path = ROOT) -> dict:
    errors, warnings = [], []
    manifest = json.loads((root / '.codex/migration-manifest.json').read_text())
    if source_snapshot(root) != manifest['sources']:
        errors.append('OpenCode/config/AGENTS source hashes changed')
    for name, expected in manifest['outputs'].items():
        path = root / name
        if not path.exists():
            errors.append(f'missing artifact or broken symlink: {name}')
        elif artifact_hash(path) != expected:
            errors.append(f'generated artifact changed: {name}')
    agents, skills = {}, {}
    for path in sorted((root / '.codex').rglob('*.toml')):
        try:
            data = tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError as exc:
            errors.append(f'{path.relative_to(root)}: {exc}')
            continue
        if path.parent.name == 'agents':
            if not all(isinstance(data.get(k), str) and data[k] for k in ('name', 'description', 'developer_instructions')):
                errors.append(f'{path.name}: invalid standalone agent metadata')
            if data.get('name') in agents:
                errors.append(f'{path.name}: duplicate agent name')
            agents[data.get('name')] = str(path.relative_to(root))
            if any(k in data for k in ('sandbox_mode', 'approval_policy', 'model_provider', 'mcp_servers')):
                errors.append(f'{path.name}: unsupported per-agent security override')
    for folder in sorted((root / '.agents/skills').iterdir()):
        path = folder / 'SKILL.md'
        if not path.is_file():
            errors.append(f'{folder.name}: missing SKILL.md')
            continue
        front = path.read_text().split('---', 2)[1]
        name = re.search(r'^name:\s*(.+)$', front, re.M)
        if not name or not re.fullmatch(r'[a-z0-9-]{1,64}', name[1]):
            errors.append(f'{folder.name}: invalid skill name')
            continue
        if name[1] in skills:
            errors.append(f'{name[1]}: duplicate skill name')
        skills[name[1]] = str(path.relative_to(root))
        # External docs may intentionally be absent; executable local scripts may not.
        for target in re.findall(r'(?<![\w/])(?:scripts|\.opencode/skills)/[\w./-]+\.(?:py|sh)\b', path.read_text()):
            candidates = [root / target, path.parent / target]
            candidates += [folder / target for folder in (root / '.agents/skills').iterdir()]
            if not any(candidate.is_file() for candidate in candidates):
                errors.append(f'{name[1]}: missing executable {target}')
    expected_agents = {row['name'] for row in manifest['inventory'] if row['kind'] == 'agent'}
    expected_skills = {row['name'] for row in manifest['inventory'] if row['kind'] in ('skill', 'command')}
    if set(agents) != expected_agents or set(skills) != expected_skills:
        errors.append(f'inventory mismatch: {len(agents)} agents, {len(skills)} skills; regenerate registry after adding skills')
    if not set(COMMANDS.values()) <= set(skills):
        errors.append('converted workflow missing')
    config = tomllib.loads((root / '.codex/config.toml').read_text())
    if any(server.get('enabled', True) for server in config.get('mcp_servers', {}).values()):
        errors.append('MCP server unexpectedly enabled')
    if config.get('approval_policy') != 'on-request' or config.get('default_permissions') != 'sdd':
        errors.append('unexpected default permissions or approval policy')
    if 'model' in config or 'model_provider' in config:
        errors.append('unexpected model/provider override')
    if not (root / 'docs/specs/constitution.md').exists():
        warnings.append('SDD roadmap not initialized: constitution absent')
    if not (root / 'docs/graphrag.md').exists():
        warnings.append('existing graph-retrieval/traceability documentation link docs/graphrag.md absent')
    return dict(status='ok' if not errors else 'error', errors=errors, warnings=warnings,
                agents=agents, skills=skills, source_files=len(manifest['sources']['files']))


class LocalClient:
    """Minimal JSONL RPC client; deliberately exposes no model-turn operation."""
    ALLOWED = {'initialize', 'skills/list', 'config/read'}

    def __init__(self, cwd: Path):
        self.logs = tempfile.TemporaryFile()
        self.process = subprocess.Popen(['codex', '--no-daemon', 'app-server', '--strict-config', '--stdio'],
            cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.logs, text=True)
        self.responses: queue.Queue = queue.Queue()
        self.next_id = 0
        def read_stdout():
            for line in self.process.stdout:
                try:
                    self.responses.put(json.loads(line))
                except ValueError:
                    pass
        self.reader = threading.Thread(target=read_stdout, daemon=True)
        self.reader.start()

    def request(self, method: str, params: dict) -> dict:
        if method not in self.ALLOWED:
            raise ValueError(f'no model/external method allowed in local probe: {method}')
        self.next_id += 1
        ident = self.next_id
        self.process.stdin.write(json.dumps({'id': ident, 'method': method, 'params': params}) + '\n')
        self.process.stdin.flush()
        while True:
            try:
                item = self.responses.get(timeout=25)
            except queue.Empty as exc:
                self.logs.seek(0)
                diagnostics = self.logs.read().decode('utf-8', errors='replace')[-2000:]
                raise ValueError(f'{method}: local protocol timeout; stderr: {diagnostics}') from exc
            if item.get('id') == ident:
                if 'error' in item:
                    raise ValueError(f'{method}: {item["error"]}')
                return item['result']

    def initialized(self):
        self.process.stdin.write('{"method":"initialized"}\n')
        self.process.stdin.flush()

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
        self.reader.join(timeout=1)
        self.process.stdin.close()
        self.process.stdout.close()
        self.logs.close()


def native_probe(root: Path = ROOT) -> dict:
    client = LocalClient(root)
    try:
        init = client.request('initialize', {'clientInfo': {'name': 'open_sdd_migration_probe', 'version': '1.0'},
                                            'capabilities': {'experimentalApi': True}})
        client.initialized()
        skill_result = client.request('skills/list', {'cwds': [str(root)], 'forceReload': True})
        config = client.request('config/read', {'cwd': str(root), 'includeLayers': True})
        # Only emit repo skill metadata and selected non-secret config details.
        entries = skill_result.get('data', [])
        found, native_errors = [], []
        for entry in entries:
            native_errors.extend(entry.get('errors', []))
            for skill in entry.get('skills', []):
                path = Path(skill['path'])
                if path.is_relative_to(root) or path.resolve().is_relative_to(root):
                    found.append({'name': skill['name'], 'path': skill['path'], 'enabled': skill.get('enabled', True)})
        layers = []
        for layer in config.get('layers') or []:
            layers.append({'name': layer.get('name'), 'disabledReason': layer.get('disabledReason'),
                           'config_keys': sorted(layer.get('config', {}))})
        # Render the model-visible tool catalog locally, without sending a model turn.
        rendered = subprocess.run(['codex', '--no-daemon', 'debug', 'prompt-input',
                                   'Migration discovery only; no action requested.'],
                                  cwd=root, capture_output=True, text=True, timeout=35)
        if rendered.returncode:
            raise ValueError(f'native prompt-input failed with exit {rendered.returncode}')
        prompt_items = json.loads(rendered.stdout)
        role_names = set()
        def visit(value):
            if isinstance(value, dict):
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
            elif isinstance(value, str) and 'Available roles:' in value:
                role_names.update(re.findall(r'^([a-z][a-z0-9_-]*): \{$', value, re.M))
        visit(prompt_items[0].get('tools', []))
        return dict(initialize='ok', repo_skills=found, skill_errors=native_errors,
                    native_agent_roles=sorted(role_names),
                    config_layers=layers, approval_policy=config.get('config', {}).get('approval_policy'),
                    native_agent_check='prompt-input tool catalog; no agent execution performed',
                    generation_requests=0)
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', action='store_true', help='probe local app-server discovery, never inference')
    args = parser.parse_args()
    try:
        result = static_check()
        if args.native:
            result['native'] = native_probe()
            names = {s['name'] for s in result['native']['repo_skills'] if s['enabled']}
            missing = set(result['skills']) - names
            if missing:
                result['errors'].append('native discovery missing: ' + ', '.join(sorted(missing)))
            missing_roles = set(result['agents']) - set(result['native']['native_agent_roles'])
            if missing_roles:
                result['errors'].append('native role catalog missing: ' + ', '.join(sorted(missing_roles)))
            if result['native']['skill_errors']:
                result['errors'].append('native skill parser errors; inspect native.skill_errors')
        result['status'] = 'ok' if not result['errors'] else 'error'
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status'] == 'ok' else 2
    except (OSError, ValueError, KeyError, queue.Empty, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc) or type(exc).__name__}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
