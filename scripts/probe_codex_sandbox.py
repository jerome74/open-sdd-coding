#!/usr/bin/env python3
"""Check installed Codex sandbox policies on disposable fixtures, never repository sources."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

CODE = '''import json
from pathlib import Path
result = {}
for name in ("workspace.txt", "raw/input.txt", ".opencode/source.txt"):
    try:
        Path(name).write_text("fixture probe")
        result[name] = "write_allowed"
    except PermissionError:
        result[name] = "write_denied"
print(json.dumps(result))
'''


def main() -> int:
    platform = 'macos' if sys.platform == 'darwin' else 'linux' if sys.platform.startswith('linux') else None
    if platform is None:
        print(json.dumps({'status': 'not_tested', 'reason': 'fixture probe supports macOS/Linux only'}))
        return 2
    with tempfile.TemporaryDirectory(prefix='codex-sdd-policy-') as directory:
        root = Path(directory).resolve()
        for name in ('raw', '.opencode'):
            (root / name).mkdir()
        (root / 'raw/input.txt').write_text('original fixture')
        (root / '.opencode/source.txt').write_text('original fixture')
        results = {}
        for mode in ('sdd', ':read-only'):
            argv = ['codex', '--cd', str(root), '-c', 'default_permissions=' + json.dumps(mode),
                    '-c', 'permissions={sdd={extends=":workspace",filesystem={":workspace_roots"={raw="read",".opencode"="read"}}}}',
                    'sandbox', '--permission-profile', mode, '--cd', str(root), '--', sys.executable, '-c', CODE]
            completed = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=20)
            if completed.returncode:
                print(json.dumps({'status': 'not_tested', 'mode': mode, 'exit_code': completed.returncode,
                                  'error': completed.stderr.strip()[-2000:]}))
                return 2
            results[mode] = json.loads(completed.stdout.strip().splitlines()[-1])
        expected = {'workspace.txt': 'write_allowed', 'raw/input.txt': 'write_denied', '.opencode/source.txt': 'write_denied'}
        ok = results['sdd'] == expected and all(value == 'write_denied' for value in results[':read-only'].values())
        ok = ok and (root / 'raw/input.txt').read_text() == 'original fixture'
        ok = ok and (root / '.opencode/source.txt').read_text() == 'original fixture'
        print(json.dumps({'status': 'ok' if ok else 'error', 'results': results, 'generation_requests': 0}, indent=2))
        return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
