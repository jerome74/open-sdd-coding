#!/usr/bin/env python3
"""Optional Codex PreToolUse RTK adapter; never executes the requested command."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys


def rewrite(event: dict) -> dict:
    if event.get('hook_event_name') != 'PreToolUse' or event.get('tool_name') not in ('Bash', 'exec_command'):
        return {}
    tool_input = event.get('tool_input', {})
    command = tool_input.get('command') if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command or not shutil.which('rtk'):
        return {}
    # Do not hide approval/denial prefixes or rewrite complex shell syntax.
    if re.search(r'[;&|<>`\n]|\$\(|\brm\b|\bpush\b', command) or command.lstrip().startswith('rtk '):
        return {}
    try:
        completed = subprocess.run(['rtk', 'rewrite', command], text=True, capture_output=True, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    updated = completed.stdout.strip()
    if completed.returncode or not updated or updated == command:
        return {}
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow',
            'updatedInput': {**tool_input, 'command': updated}}}


def main() -> int:
    try:
        event = json.load(sys.stdin)
        result = rewrite(event) if isinstance(event, dict) else {}
    except (ValueError, TypeError):
        result = {}
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
