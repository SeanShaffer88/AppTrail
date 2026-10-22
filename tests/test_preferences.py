import json
from pathlib import Path
import tempfile
import unittest
from apptrail.preferences import read_preferences, write_preference, context_lines, diff_options, DIFF_DEFAULTS


class PreferenceTests(unittest.TestCase):
    def test_diff_options_require_real_booleans(self):
        self.assertEqual(diff_options({}), DIFF_DEFAULTS)
        for invalid in (0, 1, 'true', 'false', None, [], {}):
            self.assertEqual(diff_options({key: invalid for key in DIFF_DEFAULTS}), DIFF_DEFAULTS)
        self.assertEqual(diff_options({key: not value for key, value in DIFF_DEFAULTS.items()}),
                         {key: not value for key, value in DIFF_DEFAULTS.items()})

    def test_defaults_and_validation(self):
        self.assertEqual(context_lines({}), 3)
        for value in (-1, 101, True, '5', None, [], 2.5):
            self.assertEqual(context_lines({'context_lines': value}), 3)
        for value in (0, 1, 10, 100):
            self.assertEqual(context_lines({'context_lines': value}), value)

    def test_updates_preserve_other_settings_and_survive_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'preferences.json'
            path.write_text(json.dumps({'theme': 'light', 'future': 'keep'}))
            write_preference(path, 'context_lines', 10)
            write_preference(path, 'theme', 'dark')
            self.assertEqual(read_preferences(path), {'theme': 'dark', 'future': 'keep', 'context_lines': 10})

    def test_malformed_preferences_use_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'preferences.json'
            for content in ('invalid', '[]', 'null', '{"context_lines": false}'):
                path.write_text(content)
                self.assertEqual(context_lines(read_preferences(path)), 3)
