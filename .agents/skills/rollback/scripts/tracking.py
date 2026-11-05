#!/usr/bin/env python3
"""Private-workspace change tracking and recoverable working-tree transactions (POSIX)."""
from __future__ import annotations

import argparse
import contextlib
import difflib
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True
VERSION = 1
STATE_DIR = '.rollback-state'
ABSENT = {'kind': 'absent'}
NAME = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}\Z')
RUN_ID = re.compile(r'run-[0-9a-f]{32}\Z')
HASH = re.compile(r'[0-9a-f]{64}\Z')
PROTECTED = {'.git', '.opencode', '.codex', '.agents', STATE_DIR, 'raw', 'node_modules', '.ssh', '.aws'}


class TrackingError(Exception):
    pass


class Conflict(TrackingError):
    pass


def now() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def seal(data: dict) -> dict:
    data = {k: v for k, v in data.items() if k != 'manifest_hash'}
    return dict(data, manifest_hash=digest(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()))


def validate_name(name: str) -> str:
    if not NAME.fullmatch(name):
        raise TrackingError('invalid_skill_name')
    return name


def relative(name: str) -> str:
    path = PurePosixPath(name)
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name or path.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')):
        raise TrackingError('unsafe_path')
    for index, part in enumerate(path.parts):
        lower = part.lower()
        if (lower in PROTECTED and (lower != 'raw' or index == 0)) or lower in ('auth.json', 'credentials', 'credentials.json') or lower.startswith('.env') or lower.endswith(('.pem', '.key', '.p12', '.pfx')):
            raise TrackingError('protected_or_sensitive_path: ' + name)
    return path.as_posix()


def within(name: str, scopes: list[str]) -> bool:
    return any(name == s or name.startswith(s + '/') for s in scopes)


def checked(root: Path, name: str) -> Path:
    relative(name)
    path = root
    for part in PurePosixPath(name).parts:
        path = path / part
        if path.is_symlink():
            raise TrackingError('symlink_not_supported: ' + name)
    return path


def file_state(root: Path, name: str, max_bytes: int | None = None) -> tuple[dict, bytes | None]:
    path = checked(root, name)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return dict(ABSENT), None
    except (NotADirectoryError, OSError) as exc:
        raise TrackingError('unreadable_path: ' + name) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise TrackingError('nonregular_or_hardlinked_file: ' + name)
        if max_bytes is not None and info.st_size > max_bytes:
            raise TrackingError('snapshot_budget_exceeded')
        pieces = []
        total = 0
        while chunk := os.read(fd, 1024 * 1024):
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise TrackingError('snapshot_budget_exceeded')
            pieces.append(chunk)
        data = b''.join(pieces)
        end = os.fstat(fd)
        if (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode) != (end.st_size, end.st_mtime_ns, end.st_ctime_ns, end.st_mode):
            raise Conflict('file_changed_while_reading: ' + name)
        return dict(kind='file', hash=digest(data), mode=stat.S_IMODE(info.st_mode), size=len(data)), data
    finally:
        os.close(fd)


def merge_text(base: bytes, current: bytes, desired: bytes) -> bytes:
    """Conservative three-way line merge, in memory: dry-run creates no temporary files."""
    if current == base:
        return desired
    if current == desired or desired == base:
        return current
    if any(b'\0' in x for x in (base, current, desired)):
        raise Conflict('binary_content_changed')
    try:
        b, c, d = [x.decode('utf-8').splitlines(keepends=True) for x in (base, current, desired)]
    except UnicodeError as exc:
        raise Conflict('non_utf8_content_changed') from exc
    def edits(other):
        return [(a, z, other[x:y]) for tag, a, z, x, y in difflib.SequenceMatcher(None, b, other, autojunk=False).get_opcodes() if tag != 'equal']
    left, right = edits(c), edits(d)
    for a, z, replacement in left:
        for x, y, other in right:
            if (a, z, replacement) == (x, y, other):
                continue
            if a <= y and x <= z:
                raise Conflict('overlapping_text_changes')
    combined = left + [edit for edit in right if edit not in left]
    result = list(b)
    for a, z, replacement in sorted(combined, key=lambda x: (x[0], x[1]), reverse=True):
        result[a:z] = replacement
    return ''.join(result).encode('utf-8')


class Tracker:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        self.store = self.root / STATE_DIR
        # Constructing a tracker and all plan operations are strictly read-only.
        for path in (self.store, self.store / 'runs', self.store / 'snapshots', self.store / 'workspaces'):
            if path.is_symlink():
                raise TrackingError('unsafe_tracking_storage')

    def init(self):
        for name in ('', 'runs', 'snapshots', 'workspaces', 'logs'):
            path = self.store / name
            if path.is_symlink():
                raise TrackingError('unsafe_tracking_storage')
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise TrackingError('tracking_storage_must_be_private')

    def _json(self, path: Path, data: dict):
        if path.is_symlink() or path.parent.is_symlink():
            raise TrackingError('unsafe_tracking_storage')
        temporary = path.parent / ('.' + uuid.uuid4().hex + '.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(seal(data), handle, indent=2, sort_keys=True)
                handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary.exists():
                temporary.unlink()

    def read_json(self, path: Path) -> dict:
        if path.is_symlink():
            raise TrackingError('unsafe_tracking_storage')
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise TrackingError('missing_or_corrupt_manifest') from exc
        if not isinstance(data, dict) or data.get('manifest_hash') != seal(data)['manifest_hash']:
            raise TrackingError('manifest_integrity_error')
        return data

    @contextlib.contextmanager
    def lock(self):
        self.init()
        path = self.store / '.lock'
        if path.is_symlink():
            raise TrackingError('unsafe_tracking_storage')
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Conflict('another_tracking_operation_is_running') from exc
            yield
        finally:
            os.close(fd)

    def blob(self, data: bytes) -> dict:
        h = digest(data)
        path = self.store / 'snapshots' / h
        if path.exists():
            if path.is_symlink() or digest(path.read_bytes()) != h:
                raise TrackingError('snapshot_integrity_error')
        else:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data); handle.flush(); os.fsync(handle.fileno())
        return dict(kind='file', hash=h, size=len(data))

    def data(self, state: dict) -> bytes:
        if state.get('kind') != 'file' or not HASH.fullmatch(str(state.get('hash', ''))):
            raise TrackingError('invalid_snapshot_reference')
        path = self.store / 'snapshots' / state['hash']
        try:
            if path.is_symlink():
                raise TrackingError('unsafe_snapshot')
            data = path.read_bytes()
        except OSError as exc:
            raise TrackingError('missing_snapshot') from exc
        if digest(data) != state['hash'] or len(data) != state['size']:
            raise TrackingError('snapshot_integrity_error')
        return data

    def capture(self, root: Path, name: str, persist: bool = True) -> dict:
        state, data = file_state(root, name)
        if data is not None and persist:
            self.blob(data)
        return state

    def snapshot(self, root: Path, scopes: list[str], max_bytes: int) -> dict:
        result = {}; total = 0
        for scope in scopes:
            path = checked(root, scope)
            names = []
            if path.is_dir():
                for parent, dirs, files in os.walk(path, followlinks=False):
                    for name in dirs + files:
                        child = Path(parent) / name
                        relative(child.relative_to(root).as_posix())
                        if child.is_symlink():
                            raise TrackingError('symlink_not_supported')
                    names.extend((Path(parent) / name).relative_to(root).as_posix() for name in files)
            elif path.exists():
                names.append(scope)
            for name in sorted(set(names)):
                if name in result:
                    continue
                state, data = file_state(root, name, max_bytes - total)
                total += len(data or b'')
                if total > max_bytes:
                    raise TrackingError('snapshot_budget_exceeded')
                if data is not None:
                    self.blob(data)
                result[name] = state
        return result

    def manifest_path(self, run_id: str) -> Path:
        if not RUN_ID.fullmatch(run_id):
            raise TrackingError('invalid_run_id')
        return self.store / 'runs' / (run_id + '.json')

    def load(self, run_id: str) -> dict:
        run = self.read_json(self.manifest_path(run_id))
        if run.get('schema_version') != VERSION or run.get('run_id') != run_id or run.get('repository') != str(self.root):
            raise TrackingError('run_repository_or_version_mismatch')
        validate_name(run['skill'])
        scopes = [relative(x) for x in run['scopes']]
        for entry in run.get('files', []):
            if not within(relative(entry['path']), scopes):
                raise TrackingError('run_path_outside_scope')
        return run

    def save(self, run: dict):
        self._json(self.manifest_path(run['run_id']), run)

    def runs(self) -> list[dict]:
        folder = self.store / 'runs'
        if not folder.exists():
            return []
        return [self.load(path.stem) for path in sorted(folder.glob('run-*.json'))]

    def select(self, skill: str, run_id: str | None = None) -> dict:
        validate_name(skill)
        if run_id:
            run = self.load(run_id)
            if run['skill'] != skill:
                raise TrackingError('run_belongs_to_another_skill')
            return run
        candidates = [run for run in self.runs() if run['skill'] == skill]
        if not candidates:
            raise TrackingError('no_trustworthy_tracking_for_skill: ' + skill)
        return max(candidates, key=lambda run: (run['sequence'], run['run_id']))

    def head(self) -> str | None:
        p = subprocess.run(['git', '-C', str(self.root), 'rev-parse', '--verify', 'HEAD'], capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None

    def idle(self, except_id: str | None = None):
        for run in self.runs():
            if run['run_id'] == except_id:
                continue
            if run['status'] in ('preparing', 'running', 'needs_recovery') or run.get('transaction', {}).get('state') == 'applying':
                raise Conflict('unfinished_run_requires_finish_abandon_or_recovery: ' + run['run_id'])

    def _prepare(self, skill: str, scopes: list[str], dependencies: list[str], renames: list[tuple[str, str]], max_bytes: int) -> dict:
        validate_name(skill)
        definition = self.root / '.agents/skills' / skill / 'SKILL.md'
        if not definition.is_file():
            raise TrackingError('skill_not_installed_in_repository: ' + skill)
        definition_bytes = definition.read_bytes()
        front = definition_bytes.decode('utf-8').split('---', 2)
        declared_names = [line.split(':', 1)[1].strip().strip("\"'") for line in front[1].splitlines() if line.startswith('name:')] if len(front) >= 3 else []
        if not definition_bytes.startswith(b'---') or declared_names != [skill]:
            raise TrackingError('skill_metadata_name_mismatch')
        if not scopes or max_bytes <= 0:
            raise TrackingError('explicit_paths_and_positive_budget_required')
        scopes = sorted({relative(x) for x in scopes})
        self.idle()
        ignored = subprocess.run(['git', '-C', str(self.root), 'check-ignore', '--no-index', '-q', '--', STATE_DIR + '/'], capture_output=True)
        tracked = subprocess.run(['git', '-C', str(self.root), 'ls-files', '-z', '--', STATE_DIR], capture_output=True)
        if ignored.returncode != 0 or tracked.returncode != 0 or tracked.stdout:
            raise TrackingError('tracking_storage_must_be_gitignored_and_untracked')
        for dep in dependencies:
            dependency = self.load(dep)
            if dependency['rollback_status'] == 'applied' or dependency['status'] != 'completed' or not dependency.get('published'):
                raise Conflict('dependency_unavailable_or_rolled_back')
        for source, target in renames:
            if source == target or not all(within(relative(x), scopes) for x in (source, target)):
                raise TrackingError('invalid_explicit_rename')
        run_id = 'run-' + uuid.uuid4().hex
        initial = self.snapshot(self.root, scopes, max_bytes)
        run = dict(schema_version=VERSION, repository=str(self.root), run_id=run_id, skill=skill,
                   started_at=now(), ended_at=None, sequence=max((r['sequence'] for r in self.runs()), default=0) + 1, status='preparing', workspace_ready=False, skill_definition_hash=digest(definition_bytes),
                   initial_commit=self.head(), scopes=scopes, max_bytes=max_bytes, initial=initial,
                   depends_on=dependencies, declared_renames=renames, files=[], created=[], modified=[], deleted=[],
                   errors=[], rollback_status='not_applied', attribution='private_workspace_publisher', published=False)
        self.save(run)  # Durable BEFORE execution and before workspace population.
        workspace = self.store / 'workspaces' / run_id
        workspace.mkdir(mode=0o700)
        for name, state in initial.items():
            path = workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.data(state)); path.chmod(state['mode'])
        run.update(status='running', workspace_ready=True)
        self.save(run)
        return run

    def prepare(self, skill: str, scopes: list[str], *, dependencies=None, renames=None, max_bytes=100 * 1024 * 1024) -> dict:
        with self.lock():
            return self._prepare(skill, scopes, dependencies or [], renames or [], max_bytes)

    def workspace(self, run: dict) -> Path:
        path = self.store / 'workspaces' / run['run_id']
        if path.is_symlink() or not path.is_dir():
            raise TrackingError('workspace_missing_or_unsafe')
        return path

    def _finish(self, run: dict) -> dict:
        if run['status'] != 'running' or not run.get('workspace_ready'):
            raise TrackingError('run_not_running_or_workspace_not_ready')
        workspace = self.workspace(run)
        # Refuse undeclared output rather than silently attributing broad repository changes.
        for parent, dirs, files in os.walk(workspace, followlinks=False):
            for filename in dirs + files:
                path = Path(parent) / filename
                name = path.relative_to(workspace).as_posix()
                relative(name)
                if path.is_symlink():
                    raise TrackingError('symlink_not_supported')
            for filename in files:
                name = (Path(parent) / filename).relative_to(workspace).as_posix()
                if not within(name, run['scopes']):
                    raise Conflict('workspace_output_outside_declared_scope: ' + name)
        produced = self.snapshot(workspace, run['scopes'], run['max_bytes'])
        run['produced'] = produced
        for source, target in run['declared_renames']:
            before, after = run['initial'].get(source, ABSENT), produced.get(target, ABSENT)
            if source in produced or target in run['initial'] or before.get('kind') != 'file' or before != after:
                raise Conflict('explicit_rename_not_verified')
        files, operations = [], []
        for name in sorted(set(run['initial']) | set(produced)):
            initial, after = run['initial'].get(name, ABSENT), produced.get(name, ABSENT)
            if initial == after:
                continue
            current = self.capture(self.root, name)
            desired, merged = self.resolve(initial, current, after)
            if desired == current:
                continue  # The publisher wrote nothing: never attribute a matching host edit.
            entry = dict(path=name, operation='created' if initial == ABSENT else 'deleted' if after == ABSENT else 'modified',
                         initial=initial, before=current, after=desired, produced=after, merged=merged)
            files.append(entry)
            operations.append(dict(path=name, expected=current, desired=desired))
        run['files'] = files
        for kind in ('created', 'modified', 'deleted'):
            run[kind] = [e['path'] for e in files if e['operation'] == kind]
        published_paths = {entry['path'] for entry in files}
        run['renames'] = [dict(source=a, target=b) for a, b in run['declared_renames'] if a in published_paths and b in published_paths]
        self.save(run)
        return self.transaction(run, operations, 'publish')

    def finish(self, run_id: str) -> dict:
        with self.lock():
            self.idle(run_id)
            run = self.load(run_id)
            if run['status'] != 'running' or not run.get('workspace_ready'):
                raise TrackingError('run_not_running_or_workspace_not_ready')
            try:
                return self._finish(run)
            except (TrackingError, OSError) as exc:
                if self.load(run_id).get('transaction', {}).get('state') != 'applying':
                    run.update(status='publish_conflict', ended_at=now())
                    run['errors'].append(type(exc).__name__)
                    self.save(run)
                raise

    def run(self, skill: str, scopes: list[str], command: list[str], **kwargs) -> dict:
        if not command:
            raise TrackingError('execution_command_required')
        with self.lock():
            run = self._prepare(skill, scopes, kwargs.get('dependencies', []), kwargs.get('renames', []), kwargs.get('max_bytes', 100 * 1024 * 1024))
            run['command_hash'] = digest(json.dumps(command).encode())
            run['executable'] = Path(command[0]).name  # Never persist argv, stdout, or secrets.
            self.save(run)
            try:
                code = subprocess.call(command, cwd=self.workspace(run), stdout=sys.stderr)
                run['exit_code'] = code
                if code:
                    run.update(status='failed', ended_at=now()); self.save(run)
                    return run
                return self._finish(run)
            except BaseException as exc:
                persisted = self.load(run['run_id'])
                if persisted.get('transaction', {}).get('state') != 'applying':
                    run.update(status='interrupted' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'publish_conflict', ended_at=now())
                    run['errors'].append(type(exc).__name__); self.save(run)
                raise

    def resolve(self, base: dict, current: dict, desired: dict, persist=True) -> tuple[dict, bool]:
        for state in (base, desired):
            if state != ABSENT:
                self.data(state)
        if current == desired:
            return dict(current), False
        if current == base:
            return dict(desired), False
        if any(x == ABSENT for x in (base, current, desired)):
            raise Conflict('path_reused_removed_or_created_file_changed')
        before_data, current_data, desired_data = self.data(base), self.data(current) if persist else b'', self.data(desired)
        # Dry-run current content comes directly from the working tree, not an unrecorded blob.
        if not persist:
            raise TrackingError('current_data_required_for_readonly_merge')
        data = merge_text(before_data, current_data, desired_data)
        if base['mode'] != desired['mode'] and current['mode'] != base['mode']:
            raise Conflict('permissions_changed_after_run')
        state = dict(kind='file', hash=digest(data), size=len(data), mode=desired['mode'] if current['mode'] == base['mode'] else current['mode'])
        if persist:
            self.blob(data)
        return state, True

    def preview_inverse(self, entry: dict) -> tuple[dict, bytes | None, bool]:
        before, after = entry['before'], entry['after']
        # Verify BOTH snapshots even when inverse is a no-op.
        for state in (before, after):
            if state != ABSENT:
                self.data(state)
        current, current_data = file_state(self.root, entry['path'])
        if current == before:
            return dict(current), current_data, False
        if current == after:
            return dict(before), self.data(before) if before != ABSENT else None, False
        if any(x == ABSENT for x in (before, current, after)):
            raise Conflict('path_reused_removed_or_created_file_changed')
        data = merge_text(self.data(after), current_data, self.data(before))
        if after['mode'] != before['mode'] and current['mode'] != after['mode']:
            raise Conflict('permissions_changed_after_run')
        state = dict(kind='file', hash=digest(data), size=len(data), mode=before['mode'] if current['mode'] == after['mode'] else current['mode'])
        return state, data, True

    def plan(self, skill: str, run_id: str | None = None) -> dict:
        run = self.select(skill, run_id)
        if run.get('transaction', {}).get('state') == 'applying':
            raise Conflict('recovery_required')
        if run['rollback_status'] == 'applied':
            return dict(run_id=run['run_id'], skill=skill, status='already_applied', operations=[], conflicts=[])
        if run['status'] != 'completed' or not run.get('published') or run.get('attribution') != 'private_workspace_publisher':
            raise TrackingError('run_has_no_complete_attributable_publication')
        conflicts, operations = [], []
        for other in self.runs():
            if other['run_id'] == run['run_id'] or other['rollback_status'] == 'applied' or other['status'] != 'completed':
                continue
            if run['run_id'] in other.get('depends_on', []):
                conflicts.append({'reason': 'dependent_run', 'run_id': other['run_id']})
            if other['sequence'] > run['sequence'] and set(run['created']) & set(other['initial']):
                conflicts.append({'reason': 'created_file_consumed_by_later_run', 'run_id': other['run_id']})
        for entry in run['files']:
            try:
                desired, _, merged = self.preview_inverse(entry)
                current, _ = file_state(self.root, entry['path'])
                operations.append(dict(path=entry['path'], expected=current, desired=desired, merged=merged,
                                       action='noop' if current == desired else 'remove' if desired == ABSENT else 'restore'))
            except (TrackingError, OSError) as exc:
                conflicts.append(dict(path=entry['path'], reason=str(exc)))
        return dict(run_id=run['run_id'], skill=skill, status='conflict' if conflicts else 'ready',
                    operations=operations, conflicts=conflicts, renames=run.get('renames', []))

    @contextlib.contextmanager
    def parent_fd(self, name: str):
        relative(name)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            parts = PurePosixPath(name).parts
            for part in parts[:-1]:
                try:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except FileNotFoundError:
                    os.mkdir(part, mode=0o755, dir_fd=fd)
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd); fd = child
            yield fd, parts[-1]
        finally:
            os.close(fd)

    def write(self, name: str, expected: dict, desired: dict):
        if self.capture(self.root, name, persist=False) != expected:
            raise Conflict('file_changed_before_write: ' + name)
        if expected == desired:
            return
        with self.parent_fd(name) as (parent, leaf):
            # parent components are held open with O_NOFOLLOW; never follow a swapped leaf.
            if desired == ABSENT:
                os.unlink(leaf, dir_fd=parent)
            else:
                data = self.data(desired)
                temporary = '.rollback-' + uuid.uuid4().hex + '.tmp'
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                try:
                    with os.fdopen(fd, 'wb') as handle:
                        handle.write(data); handle.flush(); os.fchmod(handle.fileno(), desired['mode']); os.fsync(handle.fileno())
                    if self.capture(self.root, name, persist=False) != expected:
                        raise Conflict('file_changed_before_replace: ' + name)
                    os.replace(temporary, leaf, src_dir_fd=parent, dst_dir_fd=parent)
                finally:
                    with contextlib.suppress(FileNotFoundError):
                        os.unlink(temporary, dir_fd=parent)
            os.fsync(parent)

    def transaction(self, run: dict, operations: list[dict], purpose: str) -> dict:
        self.idle(run['run_id'])
        for op in operations:
            if not within(relative(op['path']), run['scopes']):
                raise TrackingError('transaction_path_outside_scope')
            if self.capture(self.root, op['path']) != op['expected']:
                raise Conflict('working_tree_changed_since_plan')
            if op['desired'] != ABSENT:
                self.data(op['desired'])
        journal = dict(id=uuid.uuid4().hex, purpose=purpose, state='applying', started_at=now(),
                       previous_status=run['status'], previous_rollback_status=run['rollback_status'],
                       operations=[dict(op, state='pending') for op in operations])
        run['transaction'] = journal
        run['status'] = 'needs_recovery'
        self.save(run)  # Checkpoint of EVERY current file and write-ahead journal before writes.
        try:
            for op in journal['operations']:
                op['state'] = 'writing'; self.save(run)
                self.write(op['path'], op['expected'], op['desired'])
                op['state'] = 'applied'; self.save(run)
            receipt = dict(run_id=run['run_id'], transaction_id=journal['id'], operation=purpose,
                           time=now(), paths=[x['path'] for x in operations], current_commit=self.head())
            self._json(self.store / 'logs' / (journal['id'] + '.json'), receipt)
            journal.update(state='committed', ended_at=now())
            run.update(status='completed', ended_at=run.get('ended_at') or now())
            if purpose == 'publish':
                run['published'] = True
            else:
                run.update(rollback_status='applied', rolled_back_at=now())
            self.save(run)
        except BaseException as exc:
            run['status'] = 'needs_recovery'
            journal['state'] = 'applying'
            run['errors'].append(type(exc).__name__)
            with contextlib.suppress(OSError):
                self.save(run)
            raise
        return run

    def apply(self, skill: str, run_id: str | None = None, expected_plan: dict | None = None) -> dict:
        with self.lock():
            plan = self.plan(skill, run_id)
            if expected_plan is not None and plan != expected_plan:
                raise Conflict('plan_changed_since_confirmation')
            if plan['conflicts']:
                raise Conflict('rollback_conflicts: ' + json.dumps(plan['conflicts']))
            if plan['status'] == 'already_applied':
                return plan
            run = self.load(plan['run_id'])
            entries = {e['path']: e for e in run['files']}
            for op in plan['operations']:
                _, data, _ = self.preview_inverse(entries[op['path']])
                if data is not None:
                    self.blob(data)
            return self.transaction(run, plan['operations'], 'rollback')

    def recover(self, run_id: str) -> dict:
        with self.lock():
            self.idle(run_id)
            run = self.load(run_id)
            journal = run.get('transaction', {})
            if journal.get('state') != 'applying':
                return dict(run_id=run_id, status='no_recovery_needed')
            for op in journal['operations']:
                if not within(relative(op['path']), run['scopes']):
                    raise TrackingError('recovery_path_outside_scope')
                current = self.capture(self.root, op['path'], persist=False)
                if current not in (op['expected'], op['desired']):
                    raise Conflict('recovery_conflict: ' + op['path'])
                for state in (op['expected'], op['desired']):
                    if state != ABSENT:
                        self.data(state)
            for op in reversed(journal['operations']):
                current = self.capture(self.root, op['path'], persist=False)
                self.write(op['path'], current, op['expected'])
                op['state'] = 'recovered'; self.save(run)
            journal.update(state='recovered', ended_at=now())
            run['status'] = journal['previous_status'] if journal['purpose'] == 'rollback' else 'failed'
            run['rollback_status'] = journal['previous_rollback_status']
            if journal['purpose'] == 'publish':
                run.update(published=False, ended_at=now())
            self.save(run)
            self._json(self.store / 'logs' / (journal['id'] + '-recovery.json'), dict(operation='recovery', run_id=run_id, time=now()))
            return dict(run_id=run_id, status='recovered')

    def abandon(self, run_id: str) -> dict:
        with self.lock():
            run = self.load(run_id)
            if run['status'] not in ('preparing', 'running') or run.get('transaction', {}).get('state') == 'applying':
                raise TrackingError('cannot_abandon_transaction_use_recovery')
            run.update(status='failed', ended_at=now()); run['errors'].append('abandoned_before_publication'); self.save(run)
            return dict(run_id=run_id, status='abandoned', published=False)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('prepare', 'run'):
        item = sub.add_parser(action)
        item.add_argument('skill')
        item.add_argument('--path', action='append', dest='scopes', required=True)
        item.add_argument('--depends-on', action='append', default=[])
        item.add_argument('--rename', nargs=2, action='append', default=[], metavar=('OLD', 'NEW'))
        item.add_argument('--max-bytes', type=int, default=100 * 1024 * 1024)
    for action in ('finish', 'recover', 'abandon'):
        sub.add_parser(action).add_argument('run_id')
    sub.add_parser('status')
    # Split command at -- explicitly; argparse never executes or expands shell text.
    args_list = list(sys.argv[1:] if argv is None else argv)
    command = []
    if '--' in args_list:
        at = args_list.index('--'); args_list, command = args_list[:at], args_list[at + 1:]
    args = parser.parse_args(args_list)
    try:
        tracker = Tracker(args.repo)
        if args.action in ('prepare', 'run'):
            options = dict(dependencies=args.depends_on, renames=args.rename, max_bytes=args.max_bytes)
            result = tracker.run(args.skill, args.scopes, command, **options) if args.action == 'run' else tracker.prepare(args.skill, args.scopes, **options)
            result = {key: result[key] for key in ('run_id', 'skill', 'status', 'created', 'modified', 'deleted', 'rollback_status')}
            if args.action == 'prepare':
                result['workspace'] = str(tracker.store / 'workspaces' / result['run_id'])
        elif args.action == 'finish':
            run = tracker.finish(args.run_id)
            result = {k: run[k] for k in ('run_id', 'status', 'created', 'modified', 'deleted')}
        elif args.action == 'status':
            result = dict(runs=[{k: run[k] for k in ('run_id', 'skill', 'status', 'rollback_status')} for run in tracker.runs()],
                          storage_bytes=sum(p.stat().st_size for p in tracker.store.rglob('*') if p.is_file()) if tracker.store.exists() else 0)
        else:
            result = getattr(tracker, args.action)(args.run_id)
        print(json.dumps(result, indent=2))
        return 0 if result.get('status') not in ('failed', 'publish_conflict', 'interrupted') else 2
    except KeyboardInterrupt:
        print(json.dumps({'status': 'interrupted', 'action': 'inspect status and recover pending transactions'}))
        return 130
    except (TrackingError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
