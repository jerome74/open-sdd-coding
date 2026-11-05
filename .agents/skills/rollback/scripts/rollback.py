#!/usr/bin/env python3
"""Preview and selectively reverse a genuinely tracked skill publication."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import tracking


def plan_hash(plan: dict) -> str:
    return tracking.digest(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill')
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--run-id')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force', action='store_true', help='skip confirmation ONLY; never skip safety checks')
    parser.add_argument('--plan-hash', help='require the same preview that was confirmed')
    args = parser.parse_args(argv)
    try:
        tracker = tracking.Tracker(args.repo)
        plan = tracker.plan(args.skill, args.run_id)
        fingerprint = plan_hash(plan)
        print(json.dumps(dict(plan, plan_hash=fingerprint), indent=2))
        if args.plan_hash and args.plan_hash != fingerprint:
            raise tracking.Conflict('plan_changed_since_confirmation')
        if plan['conflicts']:
            return 2
        if args.dry_run or plan['status'] == 'already_applied':
            return 0
        if not args.force:
            if not sys.stdin.isatty():
                print(json.dumps({'status': 'confirmation_required', 'run_id': plan['run_id'], 'plan_hash': fingerprint}))
                return 3
            answer = input('Apply exactly this rollback? Type yes: ')
            if answer.strip().lower() != 'yes':
                print(json.dumps({'status': 'cancelled'}))
                return 0
        result = tracker.apply(args.skill, plan['run_id'], expected_plan=plan)
        print(json.dumps({'status': result.get('rollback_status', result.get('status')),
                          'run_id': plan['run_id'], 'operations': plan['operations']}, indent=2))
        return 0
    except KeyboardInterrupt:
        print(json.dumps({'status': 'interrupted', 'action': 'inspect tracking status; recover if transaction is applying'}))
        return 130
    except (tracking.TrackingError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
