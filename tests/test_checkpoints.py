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
        self.assertTrue(details['dirty'])  # untracked build output
        (self.project / 'code.py').write_text('modified')
        self.assertTrue(git_details(self.project)['dirty'])
        git('checkout', '--detach')
        self.assertEqual(git_details(self.project)['branch'], 'HEAD')

    def test_existing_snapshot_is_not_silently_a_checkpoint(self):
        from apptrail.core import snapshot_folder
        identity = self.history.add(snapshot_folder(self.project))
        with self.assertRaisesRegex(ValueError, 'Select a project checkpoint'):
            compare_current(self.history, identity)
