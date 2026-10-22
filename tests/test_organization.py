import copy
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from apptrail.core import compare, snapshot_folder
from apptrail.history import SnapshotHistory
from apptrail.report import render_html


class OrganizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.app = self.base / 'Demo'
        self.app.mkdir()
        (self.app / 'test.txt').write_text('same')
        self.snapshot = snapshot_folder(self.app)
        self.snapshot['completed_at'] = '2026-10-21T10:00:00+00:00'
        self.history = SnapshotHistory(self.base / 'history')
        self.old = self.history.add(self.snapshot)
        newer = copy.deepcopy(self.snapshot)
        newer['completed_at'] = '2026-10-21T11:00:00+00:00'
        self.new = self.history.add(newer)

    def tearDown(self):
        self.temp.cleanup()

    def test_names_and_notes_persist_without_changing_evidence(self):
        content = self.history.path(self.old).read_bytes()
        self.history.update_metadata(self.old, '  Release candidate ü  ', 'Commit abc123\nTests passed')
        reopened = SnapshotHistory(self.history.directory)
        entry = reopened.get(self.old)
        self.assertEqual(entry['label'], 'Release candidate ü')
        self.assertEqual(entry['notes'], 'Commit abc123\nTests passed')
        self.assertEqual(self.history.path(self.old).read_bytes(), content)
        self.assertEqual(hashlib.sha256(content).hexdigest(), self.old)
        self.assertEqual(self.history.load(self.old), self.snapshot)

    def test_search_matches_names_and_notes(self):
        self.history.update_metadata(self.old, 'Stable release', 'COMMIT abc123\nFixed startup')
        self.assertEqual([e['id'] for e in self.history.entries('stable release')], [self.old])
        self.assertEqual([e['id'] for e in self.history.entries('commit ABC123')], [self.old])

    def test_invalid_metadata_keeps_previous_values(self):
        for name, notes in (('', ''), ('a\nb', ''), ('a' * 121, ''), ('valid', 'x' * 10001), ('valid', '\0')):
            with self.subTest(name=name[:10]), self.assertRaises(ValueError):
                self.history.update_metadata(self.old, name, notes)
        self.assertEqual(self.history.get(self.old)['label'], 'Demo')

    def test_trash_restore_keeps_metadata_and_snapshot_files(self):
        self.history.update_metadata(self.old, 'Known good', 'Keep this capture')
        self.history.set_baseline(self.old)
        self.history.trash([self.old])
        self.assertEqual([e['id'] for e in self.history.entries()], [self.new])
        self.assertEqual(self.history.entries(deleted=True)[0]['notes'], 'Keep this capture')
        self.assertTrue(self.history.path(self.old).exists())
        with self.assertRaises(ValueError):
            self.history.load(self.old)
        self.history.restore([self.old])
        self.assertEqual(self.history.get(self.old)['label'], 'Known good')
        self.assertFalse(self.history.get(self.old)['baseline'])

    def test_trash_batch_is_atomic(self):
        with self.assertRaises(ValueError):
            self.history.trash([self.old, '0' * 64])
        self.assertEqual(len(self.history.entries()), 2)

    def test_reimport_restores_without_overwriting_custom_details(self):
        self.history.update_metadata(self.old, 'My name', 'My notes')
        self.history.trash([self.old])
        self.assertEqual(self.history.add(self.snapshot), self.old)
        self.assertEqual(self.history.get(self.old)['notes'], 'My notes')
        self.assertEqual(self.history.get(self.old)['label'], 'My name')

    def test_purge_requires_trash_and_leaves_original_import_untouched(self):
        source = self.base / 'original.json'
        source.write_bytes(self.history.path(self.old).read_bytes())
        with self.assertRaises(ValueError):
            self.history.purge([self.old])
        self.history.trash([self.old])
        self.history.purge([self.old])
        self.assertFalse(self.history.path(self.old).exists())
        self.assertTrue(source.exists())
        self.assertEqual(self.history.entries(deleted=True), [])
        self.assertEqual(len(self.history.entries()), 1)

    def test_purge_rolls_back_files_when_database_delete_fails(self):
        self.history.trash([self.old, self.new])
        with self.history.connect() as db:
            db.execute("CREATE TRIGGER prevent_delete BEFORE DELETE ON snapshots BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.history.purge([self.old, self.new])
        self.assertTrue(self.history.path(self.old).exists())
        self.assertTrue(self.history.path(self.new).exists())
        self.assertEqual(len(self.history.entries(deleted=True)), 2)
        self.assertEqual(list(self.history.snapshots.glob('*.pending-delete')), [])

    def test_purge_batch_validation_restores_staged_file(self):
        self.history.trash([self.old])
        with self.assertRaises(ValueError):
            self.history.purge([self.old, self.new])
        self.assertTrue(self.history.path(self.old).exists())
        self.assertTrue(self.history.path(self.new).exists())

    def test_missing_trashed_file_can_be_purged(self):
        self.history.trash([self.old])
        self.history.path(self.old).unlink()
        self.history.purge([self.old])
        self.assertEqual(self.history.entries(deleted=True), [])

    def test_baseline_is_per_folder_and_always_before_selected(self):
        self.history.set_baseline(self.new)
        pair = self.history.baseline_pair(self.old)
        self.assertEqual([identity for identity, _ in pair], [self.new, self.old])
        self.history.set_baseline(self.old)
        self.assertFalse(self.history.get(self.new)['baseline'])
        self.assertTrue(self.history.get(self.old)['baseline'])
        different = copy.deepcopy(self.snapshot)
        different['root'] = str(self.base / 'Another app')
        other = self.history.add(different)
        self.history.set_baseline(other)
        self.assertTrue(self.history.get(self.old)['baseline'])
        with self.assertRaises(ValueError):
            self.history.baseline_pair(self.old)

    def test_named_report_includes_escaped_notes_and_baseline(self):
        self.history.update_metadata(self.old, '<b>Stable</b>', 'Commit abc123\n<script>alert(1)</script>')
        self.history.set_baseline(self.old)
        result = compare(self.history.load(self.old), self.history.load(self.new))
        result['context'] = self.history.comparison_context([self.history.path(self.old), self.history.path(self.new)])
        html = render_html(result)
        self.assertIn('&lt;b&gt;Stable&lt;/b&gt;', html)
        self.assertIn('Commit abc123', html)
        self.assertIn('Baseline', html)
        self.assertNotIn('<script>', html)

    def test_upgrade_v02_catalog_preserves_existing_entry(self):
        legacy = self.base / 'legacy'
        (legacy / 'snapshots').mkdir(parents=True)
        (legacy / 'snapshots' / f'{self.old}.json').write_bytes(self.history.path(self.old).read_bytes())
        with closing(sqlite3.connect(legacy / 'history.sqlite3')) as db, db:
            db.execute('CREATE TABLE snapshots (id TEXT PRIMARY KEY, label TEXT NOT NULL, root TEXT NOT NULL, captured_at TEXT NOT NULL, captured_ts REAL NOT NULL, file_count INTEGER NOT NULL, issues INTEGER NOT NULL)')
            db.execute('INSERT INTO snapshots VALUES (?, ?, ?, ?, ?, ?, ?)', (self.old, 'Legacy', str(self.app), '2026-10-21T10:00:00+00:00', 1, 1, 0))
        upgraded = SnapshotHistory(legacy)
        self.assertEqual(upgraded.get(self.old)['notes'], '')
        self.assertEqual(upgraded.get(self.old)['label'], 'Legacy')
        self.assertEqual(upgraded.load(self.old), self.snapshot)
        SnapshotHistory(legacy)
        self.assertEqual(len(upgraded.entries()), 1)

    def test_interrupted_purge_before_commit_restores_file_on_restart(self):
        self.history.trash([self.old])
        original = self.history.path(self.old)
        staging = original.with_suffix('.' + 'a' * 32 + '.pending-delete')
        original.replace(staging)
        reopened = SnapshotHistory(self.history.directory)
        self.assertTrue(original.exists())
        self.assertFalse(staging.exists())
        self.assertEqual(len(reopened.entries(deleted=True)), 1)

    def test_interrupted_purge_after_commit_finishes_cleanup_on_restart(self):
        original = self.history.path(self.old)
        staging = original.with_suffix('.' + 'b' * 32 + '.pending-delete')
        original.replace(staging)
        with self.history.connect() as db:
            db.execute('DELETE FROM snapshots WHERE id = ?', (self.old,))
        unrelated = self.history.snapshots / 'unrelated.pending-delete'
        unrelated.write_text('Keep this file')
        SnapshotHistory(self.history.directory)
        self.assertFalse(staging.exists())
        self.assertTrue(unrelated.exists())
