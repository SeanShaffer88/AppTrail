"""Project checkpoint capture policy and read-only local Git observations."""
import fnmatch
import os
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
import subprocess

DEFAULT_EXCLUSIONS = '.git/\n__pycache__/\n.venv/\nnode_modules/'


def exclusion_rules(value):
    rules = value.splitlines() if isinstance(value, str) else list(value)
    if len(rules) > 200 or any(not isinstance(r, str) or len(r) > 500 for r in rules):
        raise ValueError('Use at most 200 exclusion patterns, each at most 500 characters.')
    rules = [r.strip().replace('\\', '/') for r in rules if r.strip()]
    if any(r.startswith(('!', '/')) or ':' in r or '..' in r.split('/') for r in rules):
        raise ValueError('Use relative glob patterns without !, drive letters, or parent paths.')
    return rules


def excluded(path, rules):
    path = path.casefold()
    parts = path.split('/')
    for rule in rules:
        pattern = rule.casefold().rstrip('/')
        if '/' not in pattern:
            if any(fnmatch.fnmatchcase(part, pattern) for part in parts):
                return True
        elif any(fnmatch.fnmatchcase('/'.join(parts[:i]), pattern) for i in range(1, len(parts) + 1)):
            return True
    return False


def _git_executable(folder):
    # Search absolute PATH entries only; Windows which() also searches CWD.
    for entry in os.get_exec_path():
        directory = Path(entry)
        if not directory.is_absolute():
            continue
        candidate = shutil.which('git', path=str(directory))
        if candidate:
            executable = Path(candidate).resolve()
            if (executable.parent == directory.resolve()
                    and not executable.is_relative_to(folder)):
                return str(executable)
    raise ValueError('Git metadata unavailable: no installed Git outside the project.')


def _git_output(command, environment, cwd, deadline):
    if time.monotonic() >= deadline:
        raise ValueError('Git metadata unavailable: observation timed out.')
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()
    with subprocess.Popen(command, cwd=cwd, env=environment, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, shell=False,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as process:
        def collect(stream, buffer):
            while chunk := stream.read1(4096):
                if len(buffer) + len(chunk) > 65536:
                    overflow.set()
                    return
                buffer.extend(chunk)
        readers = [threading.Thread(target=collect, args=(stream, buffer), daemon=True)
                   for stream, buffer in zip((process.stdout, process.stderr), buffers)]
        for reader in readers:
            reader.start()
        try:
            while process.poll() is None or any(reader.is_alive() for reader in readers):
                if overflow.is_set():
                    raise ValueError('Git metadata unavailable: output limit exceeded.')
                if time.monotonic() >= deadline:
                    raise ValueError('Git metadata unavailable: observation timed out.')
                overflow.wait(min(0.01, max(0, deadline - time.monotonic())))
            if overflow.is_set():
                raise ValueError('Git metadata unavailable: output limit exceeded.')
            return process.returncode, buffers[0].decode('utf-8', errors='replace').strip()
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            for reader in readers:
                reader.join(timeout=0.1)


def git_details(folder):
    try:
        folder = Path(folder).resolve()
        executable = _git_executable(folder)
        environment = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
        environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM=os.devnull,
                           GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
        command = [executable, '--no-pager', '--no-optional-locks', '--no-replace-objects',
                   '--no-lazy-fetch', '-c', 'log.showSignature=false', '-c', 'log.mailmap=false',
                   '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=' + os.devnull,
                   '-c', 'protocol.allow=never', '-C', str(folder)]
        deadline = time.monotonic() + 10

        def git(*args, detached=False):
            code, output = _git_output(command + list(args), environment,
                                     str(Path(executable).parent), deadline)
            if detached and code == 1:
                return 'HEAD'
            if code:
                raise ValueError('Git metadata unavailable (unsupported Git, repository, or commit).')
            return output

        top = git('rev-parse', '--show-toplevel')
        commit = git('rev-parse', '--verify', 'HEAD^{commit}')
        if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', commit):
            raise ValueError('Git metadata unavailable: invalid commit ID.')
        branch = git('symbolic-ref', '--quiet', '--short', 'HEAD', detached=True)
        metadata = git('show', '--no-patch', '--no-show-signature',
                       '--format=%s%x00%an%x00%cI', commit, '--').split('\0')
        if len(metadata) != 3:
            raise ValueError('Git metadata unavailable: malformed commit metadata.')
        subject, author, committed_at = metadata
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})', committed_at):
            raise ValueError('Git metadata unavailable: invalid commit timestamp.')
        datetime.fromisoformat(committed_at)
        return {'status': 'available', 'repository': top, 'commit': commit, 'branch': branch,
                'subject': subject, 'author': author, 'committed_at': committed_at,
                'dirty': None,
                'dirty_reason': 'Working-tree state was not inspected; metadata-only capture.'}
    except (OSError, ValueError) as exc:
        return {'status': 'unavailable', 'message': str(exc)[:500]}


def capture_checkpoint(history, folder, name, exclusions, capture_text=True,
                       progress=lambda message: None, cancelled=lambda: False):
    from .core import snapshot_folder
    name = name.strip()
    if not name or len(name) > 120 or any(ord(c) < 32 for c in name):
        raise ValueError('Choose a single-line checkpoint name of 1–120 characters.')
    root = Path(folder).resolve(strict=True)
    if root == history.directory or root in history.directory.parents or history.directory in root.parents:
        raise ValueError('Choose a project folder outside AppTrail history.')
    rules = exclusion_rules(exclusions)
    snapshot = snapshot_folder(root, progress, cancelled, capture_text=capture_text, exclusions=rules)
    snapshot['checkpoint'] = {'name': name, 'exclusions': rules, 'git': git_details(root)}
    if cancelled():
        raise InterruptedError('Checkpoint cancelled.')
    identity = history.add(snapshot, label=name)
    history.set_baseline(identity)
    return identity, snapshot


def compare_current(history, identity, progress=lambda message: None, cancelled=lambda: False):
    from .core import snapshot_folder, compare
    before = history.load(identity)
    policy = before.get('checkpoint')
    if not policy:
        raise ValueError('Select a project checkpoint created with Save checkpoint.')
    root = Path(before['root']).resolve(strict=True)
    if root == history.directory or root in history.directory.parents or history.directory in root.parents:
        raise ValueError('The project folder overlaps AppTrail history.')
    after = snapshot_folder(root, progress, cancelled,
                            capture_text=before.get('text_capture', {}).get('enabled', False),
                            exclusions=policy['exclusions'])
    after['checkpoint'] = {'name': 'Current project', 'exclusions': policy['exclusions'],
                           'git': git_details(root)}
    if cancelled():
        raise InterruptedError('Comparison cancelled.')
    current = history.add(after, label='Current · ' + policy['name'][:110])
    paths = (str(history.path(identity)), str(history.path(current)))
    result = compare(before, after)
    result['context'] = history.comparison_context(paths)
    return ('comparison', result, paths)
