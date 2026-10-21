import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from apptrail.core import snapshot_folder, save_snapshot, load_snapshot, compare
from apptrail.pe import inspect_pe, file_version
from apptrail.report import render_html


def binary(machine=0x8664, dll=b'KERNEL32.dll', delay=b'USER32.dll'):
    """Minimal PE32+ with ordinary and delay import descriptors."""
    data = bytearray(2048)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', data, 0x84, machine, 1)
    struct.pack_into('<H', data, 0x94, 240)
    opt = 0x98
    struct.pack_into('<H', data, opt, 0x20b)
    struct.pack_into('<Q', data, opt + 24, 0x140000000)
    struct.pack_into('<I', data, opt + 60, 512)
    struct.pack_into('<I', data, opt + 108, 16)
    struct.pack_into('<II', data, opt + 112 + 8, 0x1000, 40)
    struct.pack_into('<II', data, opt + 112 + 13 * 8, 0x1100, 64)
    struct.pack_into('<IIII', data, opt + 240 + 8, 1536, 0x1000, 1536, 512)
    struct.pack_into('<IIIII', data, 512, 0, 0, 0, 0x1080, 0)
    data[640:640 + len(dll) + 1] = dll + b'\0'
    struct.pack_into('<IIIIIIII', data, 768, 1, 0x1180, 0, 0, 0, 0, 0, 0)
    data[896:896 + len(delay) + 1] = delay + b'\0'
    return data


class AppTrailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.folder = self.base / 'Application ü'
        self.folder.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_full_workflow_content_and_metadata(self):
        (self.folder / 'stable.txt').write_text('same')
        (self.folder / 'changed.txt').write_text('before')
        (self.folder / 'removed.txt').write_text('remove')
        (self.folder / 'clock.txt').write_text('same')
        before = snapshot_folder(self.folder)
        save_snapshot(before, self.base / 'before.json')
        (self.folder / 'changed.txt').write_text('after!')
        (self.folder / 'removed.txt').unlink()
        (self.folder / 'added.txt').write_text('new')
        clock = self.folder / 'clock.txt'
        info = clock.stat()
        os.utime(clock, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
        after = snapshot_folder(self.folder)
        save_snapshot(after, self.base / 'after.json')
        result = compare(load_snapshot(self.base / 'before.json'), load_snapshot(self.base / 'after.json'))
        self.assertEqual(result['counts'], {'Added': 1, 'Removed': 1, 'Modified': 1, 'Metadata': 1, 'Unchanged': 1, 'Unknown': 0})
        self.assertIn('SHA-256 content hash changed.', render_html(result))

    def test_pe_architecture_and_import_changes(self):
        path = self.folder / 'demo.exe'
        path.write_bytes(binary())
        metadata = inspect_pe(path)
        self.assertEqual(metadata['architecture'], 'x64')
        self.assertEqual(metadata['imports'], ['KERNEL32.dll'])
        self.assertEqual(metadata['delay_imports'], ['USER32.dll'])
        before = snapshot_folder(self.folder)
        path.write_bytes(binary(0x14c, b'NEW.dll'))
        result = compare(before, snapshot_folder(self.folder))
        notes = ' '.join(result['changes'][0]['notes'])
        self.assertIn('Architecture: x64 → x86', notes)
        self.assertIn('New imports: NEW.dll', notes)
        self.assertIn('Removed imports: KERNEL32.dll', notes)

    def test_malformed_and_empty_files(self):
        (self.folder / 'empty.dll').write_bytes(b'')
        (self.folder / 'bad.exe').write_bytes(b'MZbad')
        result = snapshot_folder(self.folder)
        self.assertEqual(len(result['files']), 2)
        self.assertTrue(result['files'][0]['sha256'])
        self.assertIn('PE metadata unavailable', result['warnings'][0]['message'])

    def test_unstable_hash_is_not_reported_as_unchanged(self):
        path = self.folder / 'changing.txt'
        path.write_text('original')
        before = snapshot_folder(self.folder)
        def mutate(_):
            path.write_text('a different length')
        after = snapshot_folder(self.folder, progress=mutate)
        self.assertIsNone(after['files'][0]['sha256'])
        self.assertEqual(compare(before, after)['counts']['Unknown'], 1)

    def test_permission_error_preserves_unknown(self):
        path = self.folder / 'locked.txt'
        path.write_text('hello')
        before = snapshot_folder(self.folder)
        original = Path.open
        def denied(target, *args, **kwargs):
            if target == path:
                raise PermissionError('locked for test')
            return original(target, *args, **kwargs)
        with patch.object(Path, 'open', denied):
            after = snapshot_folder(self.folder)
        self.assertEqual(compare(before, after)['counts']['Unknown'], 1)
        self.assertIn('locked for test', render_html(compare(before, after)))

    def test_unreadable_directory_caveat(self):
        nested = self.folder / 'nested'
        nested.mkdir()
        (nested / 'hidden.txt').write_text('x')
        before = snapshot_folder(self.folder)
        original = os.scandir
        def denied(target):
            if Path(target) == nested:
                raise PermissionError('directory denied')
            return original(target)
        with patch('os.scandir', denied):
            after = snapshot_folder(self.folder)
        result = compare(before, after)
        self.assertIn('Capture warnings may explain', result['changes'][0]['notes'][0])
        self.assertIn('directory denied', render_html(result))

    def test_report_html_escaping(self):
        snapshot = snapshot_folder(self.folder)
        snapshot['warnings'] = [{'path': '<script>alert(1)</script>', 'message': '<img src=x onerror=alert(1)>'}]
        snapshot['root'] = '</p><script>alert(1)</script>'
        report = render_html(compare(snapshot, snapshot))
        self.assertNotIn('<script>', report)
        self.assertNotIn('<img src=x', report)
        self.assertIn('&lt;script&gt;', report)
        self.assertIn('Content-Security-Policy', report)

    def test_validation_and_output_protection(self):
        snapshot = snapshot_folder(self.folder)
        with self.assertRaises(ValueError):
            save_snapshot(snapshot, self.folder / 'snapshot.json')
        snapshot['files'] = [{'path': '../escape'}]
        path = self.base / 'invalid.json'
        path.write_text(json.dumps(snapshot))
        with self.assertRaises(ValueError):
            load_snapshot(path)
        path.write_text('{broken')
        with self.assertRaises(ValueError):
            load_snapshot(path)

    def test_cancellation(self):
        with self.assertRaises(InterruptedError):
            snapshot_folder(self.folder, cancelled=lambda: True)

    def test_command_line_workflow(self):
        (self.folder / 'file.txt').write_text('before')
        def run(*args):
            result = subprocess.run([sys.executable, '-m', 'apptrail', *map(str, args)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout
        before, after = self.base / 'before.json', self.base / 'after.json'
        report = self.base / 'report.html'
        run('snapshot', self.folder, '-o', before)
        (self.folder / 'file.txt').write_text('after')
        run('snapshot', self.folder, '-o', after)
        self.assertIn('Modified: 1', run('compare', before, after, '-o', report))
        self.assertIn('file.txt', report.read_text(encoding='utf-8'))

    def test_import_rva_outside_file_is_rejected(self):
        data = binary()
        struct.pack_into('<I', data, 524, 0x7fffffff)
        path = self.folder / 'bad-rva.exe'
        path.write_bytes(data)
        with self.assertRaises(ValueError):
            inspect_pe(path)

    def test_reparse_points_are_skipped(self):
        target = self.base / 'outside'
        target.mkdir()
        (target / 'secret.txt').write_text('outside')
        junction = self.folder / 'link'
        if os.name != 'nt':
            junction.symlink_to(target, target_is_directory=True)
        else:
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(target)], capture_output=True)
            if result.returncode:
                self.skipTest('Junction creation unavailable')
        result = snapshot_folder(self.folder)
        self.assertEqual(result['files'], [])
        self.assertIn('reparse point', result['warnings'][0]['message'])

    @unittest.skipUnless(os.name == 'nt', 'Windows version resource integration')
    def test_real_windows_binary(self):
        path = Path(os.environ['WINDIR']) / 'System32' / 'kernel32.dll'
        metadata = inspect_pe(path)
        self.assertIn(metadata['architecture'], ('x64', 'ARM64'))
        self.assertTrue(metadata['imports'])
        self.assertRegex(file_version(path), r'^\d+\.\d+\.\d+\.\d+$')


if __name__ == '__main__':
    unittest.main()
