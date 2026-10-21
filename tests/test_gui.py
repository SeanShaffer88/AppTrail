"""Exercise the real Tk workflow using an isolated library and synthetic data."""
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from apptrail.core import snapshot_folder
from apptrail.gui import AppTrail
from apptrail.history import SnapshotHistory


@unittest.skipUnless(os.name == 'nt', 'Windows Tk integration')
class HistoryGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.folder = self.base / 'Demo'
        self.folder.mkdir()
        (self.folder / 'settings.txt').write_text('before')
        self.history = SnapshotHistory(self.base / 'library')
        self.before = snapshot_folder(self.folder)
        self.before['completed_at'] = '2026-10-21T10:00:00+00:00'
        self.old_id = self.history.add(self.before)
        (self.folder / 'settings.txt').write_text('after')
        self.after = snapshot_folder(self.folder)
        self.after['completed_at'] = '2026-10-21T11:00:00+00:00'
        self.new_id = self.history.add(self.after)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = AppTrail(self.root, history=self.history)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def finish_job(self):
        deadline = time.monotonic() + 5
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertFalse(self.app.busy, 'Background operation did not finish')

    def test_startup_lists_saved_history_and_filters(self):
        self.assertEqual(len(self.app.history_tree.get_children()), 2)
        self.app.history_filter.set('no match')
        self.assertEqual(len(self.app.history_tree.get_children()), 0)
        self.app.history_filter.set('Demo')
        self.assertEqual(len(self.app.history_tree.get_children()), 2)

    def test_compare_selected_without_file_dialogs(self):
        self.app.history_tree.selection_set([self.new_id, self.old_id])
        with patch('apptrail.gui.filedialog.askopenfilename', side_effect=AssertionError('Unexpected file dialog')):
            self.app.compare_history()
            self.finish_job()
        self.assertEqual(self.app.comparison['counts']['Modified'], 1)
        self.assertEqual(self.app.before.get(), str(self.history.path(self.old_id)))
        self.assertEqual(self.app.tabs.select(), str(self.app.comparison_tab))

    def test_capture_is_automatically_saved_to_history(self):
        self.app.folder.set(str(self.folder))
        with patch('apptrail.gui.filedialog.asksaveasfilename', side_effect=AssertionError('Unexpected save dialog')):
            self.app.capture()
            self.finish_job()
        self.assertEqual(len(self.history.entries()), 3)
        self.assertEqual(len(self.app.history_tree.selection()), 1)
        self.assertEqual(self.app.tabs.select(), str(self.app.history_tab))

    def test_set_before_and_after_from_history(self):
        self.app.history_tree.selection_set(self.old_id)
        self.app.use_history(self.app.before)
        self.app.history_tree.selection_set(self.new_id)
        self.app.use_history(self.app.after)
        self.app.compare_snapshots()
        self.finish_job()
        self.assertEqual(self.app.comparison['counts']['Modified'], 1)


if __name__ == '__main__':
    unittest.main()
