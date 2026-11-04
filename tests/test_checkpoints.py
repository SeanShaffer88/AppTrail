import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from apptrail.checkpoints import capture_checkpoint, compare_current, excluded, exclusion_rules, git_details
from apptrail.core import load_snapshot
from apptrail.history import SnapshotHistory
from apptrail.report import render_html


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / 'project'
        self.project.mkdir()
        self.history = SnapshotHistory(self.base / 'history')
        (self.project / 'code.py').write_text('before')
        (self.project / 'build').mkdir()
        (self.project / 'build/output.txt').write_text('ignore')

    def test_checkpoint_persists_and_compares_current_with_same_policy(self):
        identity, before = capture_checkpoint(self.history, self.project, 'Before feature', ['build/'])
        self.assertEqual([f['path'] for f in before['files']], ['code.py'])
        self.assertEqual(self.history.get(identity)['baseline'], 1)
        (self.project / 'code.py').write_text('after')
        (self.project / 'build/output.txt').write_text('changed ignored')
        (self.project / 'new.txt').write_text('new')
        reopened = SnapshotHistory(self.base / 'history')
        result = compare_current(reopened, identity)
        self.assertEqual(result[1]['counts']['Modified'], 1)
        self.assertEqual(result[1]['counts']['Added'], 1)
        self.assertEqual(reopened.load(identity), before)
        self.assertIn('Exclusions: build/', render_html(result[1]))
        self.assertEqual(len(reopened.entries()), 2)

    def test_pattern_semantics(self):
        rules = exclusion_rules('build/\n*.log\nsrc/generated/\n.git/')
        for path in ('build/a.txt', 'nested/build/a', 'logs/a.log', 'src/generated/a', '.git/config'):
            self.assertTrue(excluded(path, rules), path)
        for path in ('builder/a', 'nested/src/generated/a', 'code.py'):
            self.assertFalse(excluded(path, rules), path)
        for invalid in ('../outside', '/absolute', '!negation', 'C:/drive'):
            with self.assertRaises(ValueError):
                exclusion_rules(invalid)

    def test_cancel_leaves_no_checkpoint(self):
        with self.assertRaises(InterruptedError):
            capture_checkpoint(self.history, self.project, 'Cancelled', [], cancelled=lambda: True)
        self.assertEqual(self.history.entries(), [])

    def test_missing_root_does_not_capture_another_folder(self):
        identity, _ = capture_checkpoint(self.history, self.project, 'Before', [])
        self.project.rename(self.base / 'moved')
        with self.assertRaises(FileNotFoundError):
            compare_current(self.history, identity)
        self.assertEqual(len(self.history.entries()), 1)

    def test_validation_and_no_git(self):
        self.assertEqual(git_details(self.project)['status'], 'unavailable')
        identity, _ = capture_checkpoint(self.history, self.project, 'Before', [])
        data = self.history.load(identity)
        data['checkpoint']['exclusions'] = ['../oops']
        file = self.base / 'invalid.json'
        file.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            load_snapshot(file)

    def test_git_commit_and_dirty_worktree(self):
        def git(*args):
            return subprocess.run(['git', '-C', str(self.project), *args], check=True, capture_output=True)
        git('init')
        git('add', 'code.py')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'Baseline commit')
        details = git_details(self.project)
        self.assertEqual(details['status'], 'available')
        self.assertEqual(details['subject'], 'Baseline commit')
        self.assertEqual(len(details['commit']), 40)
        self.assertIsNone(details['dirty'])
        self.assertTrue(details['dirty_reason'])
        (self.project / 'code.py').write_text('modified')
        self.assertIsNone(git_details(self.project)['dirty'])
        git('checkout', '--detach')
        self.assertEqual(git_details(self.project)['branch'], 'HEAD')

    def test_existing_snapshot_is_not_silently_a_checkpoint(self):
        from apptrail.core import snapshot_folder
        identity = self.history.add(snapshot_folder(self.project))
        with self.assertRaisesRegex(ValueError, 'Select a project checkpoint'):
            compare_current(self.history, identity)


class MetadataSafetyTests(unittest.TestCase):
    def test_bounded_processes(self):
        import os
        import sys
        import time
        from apptrail.checkpoints import _git_output
        for script, seconds, reason in (
                ('import os; os.write(1, b"x" * 70000)', 5, 'output limit'),
                ('import os; os.write(2, b"x" * 70000)', 5, 'output limit'),
                ('import time; time.sleep(5)', 0.1, 'timed out')):
            with self.subTest(script=script), self.assertRaisesRegex(ValueError, reason):
                _git_output([sys.executable, '-c', script], os.environ.copy(),
                            str(Path(sys.executable).parent), time.monotonic() + seconds)

    def test_executable_search_ignores_project_and_relative_path(self):
        import os
        from apptrail.checkpoints import _git_executable
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / 'git.exe').write_bytes(b'not executable')
            (root / 'git').write_bytes(b'not executable')
            with patch.dict(os.environ, {'PATH': os.pathsep.join([str(root), '.', 'relative'])}):
                with self.assertRaises(ValueError):
                    _git_executable(root)

    def test_allowlist_environment_and_malformed_metadata(self):
        import os
        calls = []
        def output(command, environment, cwd, deadline):
            calls.append(command)
            self.assertTrue(Path(command[0]).is_absolute())
            self.assertNotIn('GIT_CONFIG_COUNT', environment)
            self.assertEqual(environment['GIT_CONFIG_GLOBAL'], os.devnull)
            for flag in ('--no-lazy-fetch', '--no-replace-objects', '--no-pager',
                         'protocol.allow=never', 'core.hooksPath=' + os.devnull):
                self.assertIn(flag, command)
            return 0, next(results)
        for metadata in ('subject\0author\0' + '2026-11-03T12:00:00+00:00', 'bad', 's\0a\0bad-date'):
            results = iter(['/repo', 'a' * 40, 'main', metadata])
            with patch.dict(os.environ, {'GIT_CONFIG_COUNT': '1'}), patch(
                    'apptrail.checkpoints._git_output', side_effect=output):
                result = git_details(Path.cwd())
            self.assertEqual(result['status'], 'available' if metadata.startswith('subject') else 'unavailable')
        for command in calls:
            self.assertFalse(set(command) & {'status', 'log', 'diff'})

    def test_null_and_legacy_validation_report(self):
        from apptrail.core import snapshot_folder, compare
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = snapshot_folder(root)
            git = dict(status='available', repository='<repo>', commit='a' * 40,
                       branch='main', subject='<subject>', author='A', committed_at='date')
            data['checkpoint'] = dict(name='Checkpoint', exclusions=[], git=git)
            target = root / 'snapshot.json'
            for dirty, reason, valid in ((True, None, True), (False, None, True),
                                        (None, 'Not inspected', True), (None, '', False),
                                        (None, 'x' * 501, False), (0, None, False)):
                git['dirty'] = dirty
                git['dirty_reason'] = reason
                target.write_text(json.dumps(data))
                if valid:
                    loaded = load_snapshot(target)
                    self.assertIs(loaded['checkpoint']['git']['dirty'], dirty)
                    html = render_html(compare(loaded, loaded))
                    self.assertIn('&lt;subject&gt;', html)
                    self.assertIn('Working-tree state unknown' if dirty is None else
                                  'uncommitted changes present' if dirty else 'clean working tree', html)
                else:
                    with self.assertRaises(ValueError):
                        load_snapshot(target)
            del git['dirty']
            target.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                load_snapshot(target)

    def test_hostile_configuration_signed_commit_and_unborn(self):
        import os
        import sys
        from apptrail.checkpoints import _git_executable
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executable = _git_executable(root)
            def git(*args, input=None):
                return subprocess.run([executable, '-C', str(root), *args], input=input,
                                      check=True, capture_output=True).stdout.decode().strip()
            git('init')
            self.assertEqual(git_details(root)['status'], 'unavailable')
            sentinel = root / 'executed'
            program = root / 'sentinel.py'
            program.write_text('from pathlib import Path; Path(' + repr(str(sentinel)) + ').touch()')
            shell_command = '"' + sys.executable.replace('\\', '/') + '" "' + str(program).replace('\\', '/') + '"'
            signature_program = root / 'sentinel.cmd'
            signature_program.write_text('@' + shell_command + '\n')
            tree = git('mktree', input=b'')
            commit = (f'tree {tree}\nauthor Test <t@example.invalid> 1700000000 +0000\n'
                      'committer Test <t@example.invalid> 1700000000 +0000\n'
                      'gpgsig -----BEGIN PGP SIGNATURE-----\n fake\n -----END PGP SIGNATURE-----\n'
                      '\nSigned fixture\n')
            oid = git('hash-object', '-t', 'commit', '-w', '--stdin', input=commit.encode())
            git('update-ref', 'HEAD', oid)
            for key, value in (('core.fsmonitor', shell_command), ('filter.hostile.clean', shell_command),
                               ('gpg.program', str(signature_program)), ('log.showSignature', 'true')):
                git('config', key, value)
            (root / '.gitattributes').write_text('* filter=hostile\n')
            (root / 'untracked').write_text('content')
            with patch.dict(os.environ, {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.fsmonitor',
                                         'GIT_CONFIG_VALUE_0': shell_command}):
                observed = git_details(root)
            self.assertEqual(observed['status'], 'available', observed)
            self.assertEqual(observed['subject'], 'Signed fixture')
            self.assertFalse(sentinel.exists())

            # Positive controls: these deliberately unsafe fixture commands must run the sentinel.
            git('-c', 'core.fsmonitor=false', 'show', '--no-patch', '--show-signature', oid)
            self.assertTrue(sentinel.exists(), 'signature fixture must execute its configured program')
            sentinel.unlink()
            git('-c', 'core.fsmonitor=false', 'hash-object', '--path=untracked', '--stdin', input=b'content')
            self.assertTrue(sentinel.exists(), 'clean filter fixture must execute its configured program')
            sentinel.unlink()
            git('status', '--porcelain')
            self.assertTrue(sentinel.exists(), 'fsmonitor fixture must execute its configured program')


    def test_gui_state_labels_without_optional_highlighter(self):
        import ast
        from types import SimpleNamespace
        source = Path(__file__).resolve().parents[1] / 'apptrail' / 'gui.py'
        tree = ast.parse(source.read_text())
        method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                      and node.name == 'history_selection_changed')
        namespace = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
        info = SimpleNamespace(value='', set=lambda value: setattr(info, 'value', value),
                               get=lambda: info.value)
        git = dict(status='available', commit='abc', branch='main', subject='Subject',
                   author='Author', committed_at='Date')
        checkpoint = dict(git=git, exclusions=[])
        app = SimpleNamespace(history_tree=SimpleNamespace(selection=lambda: ['id']),
                              history_entries={'id': dict(notes='', label='Checkpoint')},
                              history=SimpleNamespace(load=lambda identity: dict(checkpoint=checkpoint)),
                              show_trash=SimpleNamespace(get=lambda: False), selection_info=info)
        for dirty, label in ((True, 'uncommitted changes present'), (False, 'clean working tree'),
                             (None, 'Working-tree state unknown — metadata-only capture.')):
            git['dirty'] = dirty
            namespace['history_selection_changed'](app)
            self.assertIn(label, info.value)
