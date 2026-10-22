import unittest
from apptrail.search import find_matches
from apptrail.textdiff import side_by_side
from tests.test_side_diff import change


class SearchTests(unittest.TestCase):
    def test_both_sides_reading_order_case_and_multiple_matches(self):
        rows = side_by_side(change('Build build\nkeep\n', 'build NEW\nkeep\n'))['rows']
        matches, limited = find_matches(rows, 'build')
        self.assertFalse(limited)
        self.assertEqual([(m['side'], m['line'], m['start'], m['end']) for m in matches],
                         [('before', 1, 0, 5), ('before', 1, 6, 11), ('after', 1, 0, 5)])
        self.assertEqual(len(find_matches(rows, 'Build', True)[0]), 1)
        self.assertEqual(len(find_matches(rows, 'keep')[0]), 2)

    def test_literal_unicode_and_whitespace(self):
        rows = side_by_side(change('😀 café = [a.*]\tend\n', '😀 CAFÉ = [a.*]\tnew\n'))['rows']
        for query, count in (('café', 2), ('[a.*]', 2), ('\t', 2), ('😀', 2), ('missing', 0), ('', 0)):
            with self.subTest(query=query):
                matches, _ = find_matches(rows, query)
                self.assertEqual(len(matches), count)
                for match in matches:
                    text = rows[match['row'] - 1][match['side']]
                    self.assertEqual(text[match['start']:match['end']].lower(), query.lower())

    def test_skips_gutters_markers_and_spacers_keeps_original_line_numbers(self):
        rows = side_by_side(change('same\n', 'new\nsame\n'))['rows']
        self.assertEqual(find_matches(rows, '1')[0], [])
        self.assertEqual(find_matches(rows, 'LF')[0], [])
        self.assertEqual(find_matches(rows, '│')[0], [])
        matches, _ = find_matches(rows, 'same')
        self.assertEqual([m['line'] for m in matches], [1, 2])
        self.assertEqual([m['row'] for m in matches], [2, 2])

    def test_explicit_match_limit_and_empty_unavailable_rows(self):
        rows = side_by_side(change('aaa', 'aaaa'))['rows']
        matches, limited = find_matches(rows, 'a', limit=3)
        self.assertEqual(len(matches), 3)
        self.assertTrue(limited)
        self.assertFalse(find_matches(rows, 'a', limit=7)[1])
        self.assertEqual(find_matches([], 'text'), ([], False))
