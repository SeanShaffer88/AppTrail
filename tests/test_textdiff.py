import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from apptrail.core import snapshot_folder, load_snapshot, save_snapshot, compare, LEGACY_SCHEMA
from apptrail.textdiff import MAX_TEXT_BYTES, MAX_TEXT_LINES, build_diff, diff_text
from apptrail.report import render_html


class TextDiffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.app = self.base / 'Demo'
        self.app.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_saved_source_diff_never_reads_live_files(self):
        source = self.app / 'main.py'
        source.write_bytes(b'def answer():\n    return 41\n')
        before = snapshot_folder(self.app)
        source.write_bytes(b'def answer():\n    return 42\n')
        after = snapshot_folder(self.app)
        source.unlink()
        model = build_diff(compare(before, after)['changes'][0])
        text = diff_text(model)
        self.assertEqual(model['state'], 'available')
        self.assertIn('-    return 41\n', text)
        self.assertIn('+    return 42\n', text)
        self.assertIn('@@ -1,2 +1,2 @@', text)
        self.assertEqual((model['added'], model['removed']), (1, 1))

    def test_encodings_round_trip_with_matching_hash(self):
        for codec, bom in (('utf-8', b''), ('utf-8', b'\xef\xbb\xbf'), ('utf-16-le', b'\xff\xfe'),
                           ('utf-16-be', b'\xfe\xff'), ('utf-32-le', b'\xff\xfe\0\0'), ('utf-32-be', b'\0\0\xfe\xff')):
            with self.subTest(codec=codec, bom=bom):
                raw = bom + 'name = "café"\r\n'.encode(codec)
                (self.app / 'settings.ini').write_bytes(raw)
                snapshot = snapshot_folder(self.app)
                save_snapshot(snapshot, self.base / 'snapshot.json')
                entry = load_snapshot(self.base / 'snapshot.json')['files'][0]
                self.assertEqual(entry['text_status'], 'captured')
                self.assertEqual(entry['text']['content'].encode(entry['text']['encoding']), raw)
                self.assertEqual(entry['sha256'], hashlib.sha256(raw).hexdigest())

    def test_common_credentials_and_private_git_content_are_excluded(self):
        for name in ('.env', '.env.local', '.env.example', 'credentials.json', 'secrets.yaml', '.npmrc'):
            (self.app / name).write_text('PRIVATE_TEST_VALUE')
        private = self.app / '.git'
        private.mkdir()
        (private / 'config.json').write_text('PRIVATE_TEST_VALUE')
        snapshot = snapshot_folder(self.app)
        self.assertTrue(all(e['text_status'] == 'excluded' and e['text'] is None and e['sha256'] for e in snapshot['files']))
        self.assertNotIn('PRIVATE_TEST_VALUE', json.dumps(snapshot))

    def test_binary_invalid_utf8_and_unknown_extension_are_not_captured(self):
        (self.app / 'binary.txt').write_bytes(b'hello\0world')
        (self.app / 'legacy.ini').write_bytes(b'caf\xe9')
        (self.app / 'image.png').write_bytes(b'ascii but an image extension')
        entries = {e['path']: e for e in snapshot_folder(self.app)['files']}
        self.assertEqual(entries['binary.txt']['text_status'], 'unsupported')
        self.assertEqual(entries['legacy.ini']['text_status'], 'unsupported')
        self.assertEqual(entries['image.png']['text_status'], 'not_eligible')

    def test_file_and_line_limits(self):
        (self.app / 'large.txt').write_bytes(b'x' * (MAX_TEXT_BYTES + 1))
        (self.app / 'many.txt').write_bytes(b'x\n' * (MAX_TEXT_LINES + 1))
        entries = {e['path']: e for e in snapshot_folder(self.app)['files']}
        self.assertEqual(entries['large.txt']['text_status'], 'too_large')
        self.assertEqual(entries['many.txt']['text_status'], 'line_limit')
        self.assertTrue(all(e['text'] is None and e['sha256'] for e in entries.values()))

    def test_total_budget_and_disabled_capture(self):
        (self.app / 'a.txt').write_bytes(b'hello')
        (self.app / 'b.txt').write_bytes(b'world')
        with patch('apptrail.core.MAX_TOTAL_TEXT_BYTES', 8):
            snapshot = snapshot_folder(self.app)
        self.assertEqual(snapshot['text_capture']['captured_bytes'], 5)
        self.assertEqual(snapshot['files'][1]['text_status'], 'budget_exceeded')
        disabled = snapshot_folder(self.app, capture_text=False)
        self.assertFalse(disabled['text_capture']['enabled'])
        self.assertTrue(all(e['text'] is None and e['text_status'] == 'disabled' for e in disabled['files']))

    def test_unstable_file_discards_saved_text(self):
        source = self.app / 'test.py'
        source.write_text('x = 1\n')
        def mutate(_):
            source.write_text('x = 10000000\n')
        snapshot = snapshot_folder(self.app, progress=mutate)
        self.assertIsNone(snapshot['files'][0]['text'])
        self.assertEqual(snapshot['files'][0]['text_status'], 'unstable')
        self.assertEqual(snapshot['text_capture']['captured_bytes'], 0)

    def test_added_removed_and_empty_text_files(self):
        before = snapshot_folder(self.app)
        (self.app / 'new.json').write_text('{"enabled":true}\n')
        after = snapshot_folder(self.app)
        added = build_diff(compare(before, after)['changes'][0])
        self.assertIn('+{"enabled":true}', diff_text(added))
        self.assertIn('--- /dev/null', diff_text(added))
        removed = build_diff(compare(after, before)['changes'][0])
        self.assertIn('-{"enabled":true}', diff_text(removed))
        self.assertIn('+++ /dev/null', diff_text(removed))
        (self.app / 'new.json').write_bytes(b'')
        empty = build_diff(compare(before, snapshot_folder(self.app))['changes'][0])
        self.assertIn('empty text file', empty['message'])

    def test_line_endings_and_missing_final_newline_are_explicit(self):
        path = self.app / 'settings.ini'
        path.write_bytes(b'enabled=true\r\n')
        before = snapshot_folder(self.app)
        path.write_bytes(b'enabled=true')
        model = build_diff(compare(before, snapshot_folder(self.app))['changes'][0])
        text = diff_text(model, show_endings=True)
        self.assertIn('⟦CRLF⟧', text)
        self.assertIn('⟦no final newline⟧', text)
        self.assertIn('\\ No newline at end of file', text)
        self.assertIn('CRLF: 1', model['before_summary'])

    def test_encoding_only_change_does_not_invent_line_edits(self):
        path = self.app / 'settings.ini'
        path.write_bytes(b'\xef\xbb\xbfx=1\n')
        before = snapshot_folder(self.app)
        path.write_bytes(b'x=1\n')
        model = build_diff(compare(before, snapshot_folder(self.app))['changes'][0])
        self.assertEqual(model['lines'], [])
        self.assertIn('byte-order mark', model['message'])

    def test_source_lines_that_look_like_headers_are_still_edits(self):
        path = self.app / 'test.txt'
        path.write_bytes(b'-- old\n')
        before = snapshot_folder(self.app)
        path.write_bytes(b'++ new\n')
        model = build_diff(compare(before, snapshot_folder(self.app))['changes'][0])
        self.assertEqual((model['added'], model['removed']), (1, 1))

    def test_legacy_snapshot_loads_but_cannot_reconstruct_modified_text(self):
        path = self.app / 'settings.json'
        path.write_text('{"a":1}')
        legacy = snapshot_folder(self.app)
        legacy['schema'] = LEGACY_SCHEMA
        legacy.pop('text_capture')
        for entry in legacy['files']:
            entry.pop('text')
            entry.pop('text_status')
        save_snapshot(legacy, self.base / 'legacy.json')
        path.write_text('{"a":2}')
        model = build_diff(compare(load_snapshot(self.base / 'legacy.json'), snapshot_folder(self.app))['changes'][0])
        self.assertEqual(model['state'], 'unavailable')
        self.assertIn('older snapshot', model['message'])
        self.assertEqual(model['lines'], [])

    def test_forged_text_or_incorrect_budget_is_rejected(self):
        (self.app / 'settings.json').write_text('{"a":1}')
        snapshot = snapshot_folder(self.app)
        forged = copy.deepcopy(snapshot)
        forged['files'][0]['text']['content'] = '{"a":2}'
        target = self.base / 'bad.json'
        target.write_text(json.dumps(forged), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            load_snapshot(target)
        snapshot['text_capture']['captured_bytes'] += 1
        target.write_text(json.dumps(snapshot), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'byte count'):
            load_snapshot(target)

    def test_report_contains_escaped_saved_diff_and_content_notice(self):
        path = self.app / 'page.html'
        path.write_text('<p>old</p>\n')
        before = snapshot_folder(self.app)
        path.write_text('<script>alert(1)</script>\n')
        report = render_html(compare(before, snapshot_folder(self.app)))
        self.assertIn('Show saved text diff', report)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', report)
        self.assertNotIn('<script>', report)
        self.assertIn('saved source/config contents', report)
        self.assertIn('diff-add', report)

    def test_cli_opt_out_does_not_capture_contents(self):
        (self.app / 'settings.json').write_text('PRIVATE_TEST_CONTENT')
        output = self.base / 'no-text.json'
        result = subprocess.run([sys.executable, '-m', 'apptrail', 'snapshot', str(self.app), '-o', str(output), '--no-text'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('PRIVATE_TEST_CONTENT', output.read_text(encoding='utf-8'))
        self.assertFalse(load_snapshot(output)['text_capture']['enabled'])

    def test_report_marks_oversized_escaped_diff_instead_of_silent_truncation(self):
        path = self.app / 'large.txt'
        path.write_bytes(b'<' * MAX_TEXT_BYTES)
        before = snapshot_folder(self.app)
        path.write_bytes(b'>' * MAX_TEXT_BYTES)
        report = render_html(compare(before, snapshot_folder(self.app)))
        self.assertIn('exceeds the remaining report diff budget', report)
        self.assertLess(len(report), 30000)


if __name__ == '__main__':
    unittest.main()
