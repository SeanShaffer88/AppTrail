import unittest
from apptrail.syntax import highlight_lines


class SyntaxTests(unittest.TestCase):
    def test_python_multiline_strings_crlf_and_no_final_newline(self):
        language, rows = highlight_lines('demo.py', 'def build():\r\n    """first\r\n    last"""\r\n    return 42 # count')
        self.assertEqual(language, 'Python')
        self.assertEqual(len(rows), 4)
        self.assertIn((0, 3, 'keyword'), rows[0])
        self.assertTrue(any(kind == 'string' for _, _, kind in rows[2]))
        self.assertTrue(any(kind == 'number' for _, _, kind in rows[3]))
        self.assertTrue(any(kind == 'comment' for _, _, kind in rows[3]))

    def test_config_formats_and_named_files(self):
        for path, content, expected in (
            ('a.json', '{"enabled": true, "count": 4}', 'JSON'),
            ('a.yaml', 'enabled: true\n', 'YAML'), ('a.toml', '[build]\ncount = 4', 'TOML'),
            ('a.ini', '[build]\ncount=4', 'INI'), ('.editorconfig', '[*.py]\nindent_size=4', 'INI'),
            ('app.config', '<?xml version="1.0"?><settings />', 'XML'),
            ('a.ts', 'const count: number = 4;', 'TypeScript'),
            ('a.cs', 'class Build { int count = 4; }', 'C#'),
            ('Dockerfile', 'FROM python:3.15', 'Docker'),
        ):
            with self.subTest(path=path):
                name, spans = highlight_lines(path, content)
                self.assertIn(expected, name)
                self.assertTrue(any(spans))

    def test_plain_fallback_empty_and_bom(self):
        self.assertEqual(highlight_lines('unknown.foo', 'return 42'), ('Plain text', [[]]))
        self.assertEqual(highlight_lines('empty.py', '')[1], [])
        self.assertEqual(highlight_lines('bom.py', '\ufeffreturn 42'), highlight_lines('bom.py', 'return 42'))

    def test_highlighted_ranges_stay_inside_original_display_lines(self):
        content = 'emoji = "😀"; return 42\n\t# comment\n'
        _, rows = highlight_lines('demo.py', content)
        for line, spans in zip(content.splitlines(), rows):
            for start, end, _ in spans:
                self.assertTrue(0 <= start < end <= len(line))
