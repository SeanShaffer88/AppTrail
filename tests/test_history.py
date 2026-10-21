import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from apptrail.core import compare, snapshot_folder
from apptrail.history import SnapshotHistory, history_directory


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.app = self.base / 'Demo ü'
        self.app.mkdir()
        (self.app / 'settings.txt').write_text('before', encoding='utf-8')
        self.snapshot = snapshot_folder(self.app)
        self.snapshot['completed_at'] = '2026-10-21T10:00:00+00:00'
        self.history = SnapshotHistory(self.base / 'history')

    def tearDown(self):
        self.temp.cleanup()

    def test_persistence_and_owned_copy(self):
        source = self.base / 'old.json'
        source.write_text(json.dumps(self.snapshot), encoding='utf-8')
        identity = self.history.import_file(source)
        source.unlink()
        reopened = SnapshotHistory(self.history.directory)
        self.assertEqual(reopened.entries()[0]['id'], identity)
        self.assertEqual(reopened.load(identity), self.snapshot)

    def test_identical_imports_are_deduplicated(self):
        identity = self.history.add(self.snapshot)
        source = self.base / 'formatted.json'
        source.write_text(json.dumps(self.snapshot, separators=(',', ':')), encoding='utf-8')
        self.assertEqual(self.history.import_file(source), identity)
        self.assertEqual(len(self.history.entries()), 1)

    def test_search_and_issue_summary(self):
        self.snapshot['warnings'] = [{'path': 'locked', 'message': 'Read failed'}]
        self.snapshot['files'][0]['error'] = 'File changed'
        identity = self.history.add(self.snapshot)
        entries = self.history.entries('DEMO Ü')
        self.assertEqual(entries[0]['id'], identity)
        self.assertEqual(entries[0]['issues'], 2)
        self.assertEqual(entries[0]['file_count'], 1)
        self.assertEqual(self.history.entries('no match'), [])

    def test_pair_is_chronological_across_timezones(self):
        old = self.history.add(self.snapshot)
        (self.app / 'settings.txt').write_text('after', encoding='utf-8')
        after = snapshot_folder(self.app)
        after['completed_at'] = '2026-10-21T06:00:00-05:00'
        new = self.history.add(after)
        self.assertEqual([e['id'] for e in self.history.entries()], [new, old])
        pair = self.history.compare_pair([new, old])
        self.assertEqual([identity for identity, _ in pair], [old, new])
        self.assertEqual(compare(pair[0][1], pair[1][1])['counts']['Modified'], 1)

    def test_invalid_import_does_not_pollute_history(self):
        source = self.base / 'bad.json'
        source.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.history.import_file(source)
        self.assertEqual(self.history.entries(), [])
        self.assertEqual(list(self.history.snapshots.iterdir()), [])

    def test_invalid_date_does_not_create_a_file(self):
        invalid = copy.deepcopy(self.snapshot)
        invalid['completed_at'] = 'not a date'
        with self.assertRaises(ValueError):
            self.history.add(invalid)
        self.assertEqual(list(self.history.snapshots.iterdir()), [])

    def test_missing_snapshot_is_visible_and_can_be_restored(self):
        identity = self.history.add(self.snapshot)
        self.history.path(identity).unlink()
        self.assertFalse(self.history.entries()[0]['available'])
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.history.load(identity)
        self.history.add(self.snapshot)
        self.assertTrue(self.history.entries()[0]['available'])
        self.assertEqual(self.history.load(identity), self.snapshot)

    def test_modified_library_json_is_not_silently_trusted(self):
        identity = self.history.add(self.snapshot)
        self.history.path(identity).write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed outside'):
            self.history.load(identity)
        with self.assertRaisesRegex(ValueError, 'changed outside'):
            self.history.load_path(self.history.path(identity))

    def test_external_json_remains_compatible(self):
        source = self.base / 'external.json'
        source.write_text(json.dumps(self.snapshot), encoding='utf-8')
        self.assertEqual(self.history.load_path(source), self.snapshot)

    def test_pair_selection_validation(self):
        identity = self.history.add(self.snapshot)
        for selection in ([], [identity], [identity, identity], [identity, '0' * 64]):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                self.history.compare_pair(selection)

    def test_multiple_instances_do_not_drop_entries(self):
        another = SnapshotHistory(self.history.directory)
        self.history.add(self.snapshot)
        changed = copy.deepcopy(self.snapshot)
        changed['completed_at'] = '2026-10-21T12:00:00+00:00'
        another.add(changed)
        self.assertEqual(len(self.history.entries()), 2)

    def test_failed_json_write_creates_no_catalog_row(self):
        with patch('apptrail.history.atomic_write', side_effect=PermissionError('write denied')):
            with self.assertRaises(PermissionError):
                self.history.add(self.snapshot)
        self.assertEqual(self.history.entries(), [])

    def test_invalid_identity_cannot_escape_library(self):
        with self.assertRaises(ValueError):
            self.history.load('../outside.json')

    def test_windows_profile_location(self):
        with patch('apptrail.history.os.name', 'nt'), patch.dict('os.environ', {'LOCALAPPDATA': str(self.base)}):
            self.assertEqual(history_directory(), self.base / 'AppTrail' / 'history')


if __name__ == '__main__':
    unittest.main()
