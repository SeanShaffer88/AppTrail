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

    def test_editor_saves_name_notes_and_searches_them(self):
        self.app.history_tree.selection_set(self.old_id)
        editor = self.app.edit_history()
        editor.name.set('Release candidate')
        editor.notes.insert('1.0', 'Commit abc123\nTests passed')
        editor.save()
        self.assertEqual(self.history.get(self.old_id)['label'], 'Release candidate')
        self.app.history_filter.set('abc123')
        self.assertEqual(self.app.history_tree.get_children(), (self.old_id,))

    def test_trash_and_restore_clear_comparison_inputs(self):
        self.app.history_tree.selection_set([self.old_id, self.new_id])
        self.app.compare_history()
        self.finish_job()
        self.app.history_tree.selection_set(self.old_id)
        with patch('apptrail.gui.messagebox.askyesno', return_value=True):
            self.app.trash_history()
        self.assertIsNone(self.app.comparison)
        self.assertEqual(self.app.before.get(), '')
        self.assertNotIn(self.old_id, self.app.history_tree.get_children())
        self.app.show_trash.set(True)
        self.app.refresh_history()
        self.app.history_tree.selection_set(self.old_id)
        self.app.restore_history()
        self.app.show_trash.set(False)
        self.app.refresh_history()
        self.assertIn(self.old_id, self.app.history_tree.get_children())

    def test_delete_confirmation_can_be_cancelled(self):
        self.app.history_tree.selection_set(self.old_id)
        with patch('apptrail.gui.messagebox.askyesno', return_value=False):
            self.app.trash_history()
        self.assertEqual(len(self.history.entries()), 2)

    def test_baseline_comparison_includes_names_and_notes(self):
        self.history.update_metadata(self.old_id, 'Known good', 'Commit abc123')
        self.app.history_tree.selection_set(self.old_id)
        self.app.mark_baseline()
        self.app.history_tree.selection_set(self.new_id)
        self.app.compare_baseline()
        self.finish_job()
        self.assertEqual(self.app.comparison['counts']['Modified'], 1)
        self.assertEqual(self.app.comparison['context']['before']['label'], 'Known good')
        self.assertEqual(self.app.comparison['context']['before']['notes'], 'Commit abc123')

    def test_permanent_delete_requires_trash_view_and_confirmation(self):
        self.history.trash([self.old_id])
        self.app.show_trash.set(True)
        self.app.refresh_history()
        self.app.history_tree.selection_set(self.old_id)
        with patch('apptrail.gui.messagebox.askyesno', return_value=True):
            self.app.purge_history()
        self.assertFalse(self.history.path(self.old_id).exists())
        self.assertEqual(self.history.entries(deleted=True), [])

    def test_text_diff_window_renders_saved_lines_and_colors(self):
        self.app.history_tree.selection_set([self.old_id, self.new_id])
        self.app.compare_history()
        self.finish_job()
        self.app.tree.selection_set('0')
        window = self.app.details()
        try:
            self.assertEqual(window.model['state'], 'available')
            self.assertIn('-before', window.text.get('1.0', 'end'))
            self.assertIn('+after', window.text.get('1.0', 'end'))
            self.assertTrue(window.text.tag_ranges('add'))
            self.assertTrue(window.text.tag_ranges('remove'))
            window.show_endings.set(True)
            window.refresh_diff()
            self.assertIn('no final newline', window.text.get('1.0', 'end'))
        finally:
            window.destroy()

    def test_desktop_text_capture_can_be_disabled(self):
        self.app.folder.set(str(self.folder))
        self.app.include_text.set(False)
        self.app.capture()
        self.finish_job()
        identity = self.app.history_tree.selection()[0]
        snapshot = self.history.load(identity)
        self.assertFalse(snapshot['text_capture']['enabled'])
        self.assertIsNone(snapshot['files'][0]['text'])

    def test_terminal_default_toggle_persists_and_updates_open_diff(self):
        from apptrail.gui import TextDiffWindow, SnapshotEditor
        from apptrail.theme import Theme, PALETTES
        from tests.test_side_diff import change
        self.assertEqual(self.app.theme.mode.get(), 'dark')
        window = TextDiffWindow(self.root, change('return 1\n', 'return 2\n'))
        editor = SnapshotEditor(self.root, self.history, self.history.get(self.old_id), lambda _: None)
        try:
            widget = window.side_texts[1]
            original = widget.get('1.0', 'end')
            self.assertEqual(widget.cget('background'), PALETTES['dark']['field'])
            self.assertEqual(editor.notes.cget('background'), PALETTES['dark']['field'])
            self.assertEqual(widget.get(*widget.tag_ranges('syntax_keyword')[:2]), 'return')
            window.jump_change(1)
            self.app.theme.toggle()
            self.assertEqual(widget.cget('background'), PALETTES['light']['field'])
            self.assertEqual(widget.tag_cget('syntax_keyword', 'foreground'), PALETTES['light']['keyword'])
            self.assertEqual(widget.tag_cget('changed', 'background'), PALETTES['light']['add'])
            self.assertEqual(widget.get('1.0', 'end'), original)
            self.assertEqual(window.position.get(), 'Change 1 of 1')
            self.assertTrue(widget.tag_ranges('current'))
            restored = Theme(self.root, self.history.directory / 'preferences.json')
            self.assertEqual(restored.mode.get(), 'light')
        finally:
            editor.destroy()
            window.destroy()

    def test_syntax_alignment_survives_insertions_unicode_and_refresh(self):
        from apptrail.gui import TextDiffWindow
        from tests.test_side_diff import change
        window = TextDiffWindow(self.root, change('return 1\n', 'label = "😀"; return 2\nreturn 1\n'))
        try:
            widget = window.side_texts[1]
            self.assertEqual(widget.get(*widget.tag_ranges('syntax_keyword')[:2]), 'return')
            window.show_endings.set(True)
            window.refresh_diff()
            self.assertEqual(widget.get(*widget.tag_ranges('syntax_keyword')[:2]), 'return')
            self.assertIn('⟦LF⟧', widget.get('1.0', 'end'))
            self.assertTrue(window.side_texts[0].tag_ranges('spacer'))
        finally:
            window.destroy()

    def test_malformed_theme_setting_falls_back_to_dark(self):
        from apptrail.theme import Theme
        path = self.history.directory / 'preferences.json'
        for value in ('invalid json', '{"theme": []}', '{"theme": "unknown"}', '[]'):
            path.write_text(value)
            self.assertEqual(Theme(self.root, path).mode.get(), 'dark')

    def test_word_highlights_survive_theme_endings_and_navigation(self):
        from apptrail.gui import TextDiffWindow
        from apptrail.theme import PALETTES
        from tests.test_side_diff import change
        window = TextDiffWindow(self.root, change('label = "😀"; return 2\r\n', 'label = "😀"; return 4\n'))
        try:
            left, right = window.side_texts
            self.assertEqual(left.get(*left.tag_ranges('word_change')[:2]), '2')
            self.assertEqual(right.get(*right.tag_ranges('word_change')[:2]), '4')
            self.assertEqual(right.get(*right.tag_ranges('syntax_keyword')[:2]), 'return')
            window.jump_change(1)
            window.show_endings.set(True)
            window.refresh_diff()
            ranges = right.tag_ranges('word_change')
            self.assertIn('⟦LF⟧', right.get(ranges[-2], ranges[-1]))
            self.app.theme.toggle()
            self.assertEqual(right.tag_cget('word_change', 'background'), PALETTES['light']['word_add'])
            window.show_words.set(False)
            window.refresh_diff()
            self.assertFalse(right.tag_ranges('word_change'))
            self.assertTrue(right.tag_ranges('changed'))
            self.assertTrue(right.tag_ranges('syntax_keyword'))
            self.assertEqual(window.position.get(), 'Change 1 of 1')
            window.show_words.set(True)
            window.refresh_diff()
            self.assertTrue(right.tag_ranges('word_change'))
        finally:
            window.destroy()

    def test_search_navigation_refresh_clear_and_theme(self):
        from apptrail.gui import TextDiffWindow
        from apptrail.theme import PALETTES
        from tests.test_side_diff import change
        window = TextDiffWindow(self.root, change('😀 Build build\n', '😀 build new\n'))
        try:
            window.search_query.set('build')
            window.update_search()
            self.assertEqual(len(window.search_matches), 3)
            self.assertEqual(window.search_status.get(), 'Match 1 of 3 · Before line 1')
            left, right = window.side_texts
            self.assertEqual(left.get(*left.tag_ranges('search_current')), 'Build')
            window.jump_match(1)
            self.assertEqual(left.get(*left.tag_ranges('search_current')), 'build')
            window.jump_match(1)
            self.assertEqual(window.search_status.get(), 'Match 3 of 3 · After line 1')
            self.assertEqual(right.get(*right.tag_ranges('search_current')), 'build')
            self.app.theme.toggle()
            self.assertEqual(right.tag_cget('search_current', 'background'), PALETTES['light']['search_active'])
            window.show_words.set(False)
            window.show_endings.set(True)
            window.refresh_diff()
            self.assertEqual(window.match_index, 2)
            self.assertTrue(right.tag_ranges('search_current'))
            window.jump_match(1)
            self.assertEqual(window.match_index, 0)
            window.jump_match(-1)
            self.assertEqual(window.match_index, 2)
            window.match_case.set(True)
            window.search_query.set('Build')
            window.update_search()
            self.assertEqual(len(window.search_matches), 1)
            window.search_query.set('missing')
            window.update_search()
            self.assertEqual(window.search_status.get(), 'No matches in saved text')
            self.assertIn('disabled', window.next_match.state())
            window.clear_search()
            self.assertFalse(left.tag_ranges('search_match'))
            self.assertFalse(right.tag_ranges('search_current'))
        finally:
            window.destroy()

    def test_search_reveals_offscreen_match_and_cancels_pending_on_close(self):
        from apptrail.gui import TextDiffWindow
        from tests.test_side_diff import change
        before = ''.join(f'row {i}\n' for i in range(100))
        after = before + ' ' * 200 + 'needle\n'
        window = TextDiffWindow(self.root, change(before, after))
        self.root.update()
        window.search_query.set('needle')
        window.jump_match(-1)
        self.root.update()
        self.assertEqual(window.search_status.get(), 'Match 1 of 1 · After line 101')
        self.assertTrue(window.side_texts[1].bbox('101.207'))
        window.search_query.set('row')
        pending = window.search_pending
        self.assertIsNotNone(pending)
        window.destroy()
        self.assertIsNone(window.search_pending)
        self.assertNotIn(pending, self.root.tk.call('after', 'info'))

    def test_side_diff_navigation_numbers_and_synchronized_scrolling(self):
        from apptrail.gui import TextDiffWindow
        from tests.test_side_diff import change
        before = [f'line {i}\n' for i in range(100)]
        after = list(before)
        after[3] = 'first edit\n'
        after[80] = 'second edit\n'
        window = TextDiffWindow(self.root, change(''.join(before), ''.join(after)))
        try:
            self.root.update()
            self.assertEqual(window.tabs.index(window.tabs.select()), 0)
            self.assertIn('   4 │ first edit', window.side_texts[1].get('1.0', 'end'))
            window.jump_change(1)
            self.assertEqual(window.position.get(), 'Change 1 of 2')
            window.jump_change(1)
            self.assertEqual(window.position.get(), 'Change 2 of 2')
            self.assertEqual(str(window.side_texts[0].tag_ranges('current')[0]), '81.0')
            self.root.update()
            self.assertAlmostEqual(window.side_texts[0].yview()[0], window.side_texts[1].yview()[0], places=3)
            window.jump_change(1)
            self.assertEqual(window.position.get(), 'Change 1 of 2')
            window.jump_change(-1)
            self.assertEqual(window.position.get(), 'Change 2 of 2')
            window.show_endings.set(True)
            window.refresh_diff()
            self.assertIn('⟦LF⟧', window.side_texts[1].get('1.0', 'end'))
            self.assertEqual(window.position.get(), 'Change 2 of 2')
        finally:
            window.destroy()


if __name__ == '__main__':
    unittest.main()
