import unittest
from apptrail.folding import unchanged_ranges


def rows(count, changes=()):
    return [{'kind': 'replace' if index in changes else 'equal'} for index in range(1, count + 1)]


class FoldingTests(unittest.TestCase):
    def test_retains_three_context_rows_around_both_changes(self):
        self.assertEqual(unchanged_ranges(rows(40, (10, 30))), [(1, 7), (14, 27), (34, 41)])

    def test_short_runs_and_adjacent_context_are_not_folded(self):
        self.assertEqual(unchanged_ranges(rows(8, (4, 5))), [])
        self.assertEqual(unchanged_ranges(rows(10, (5, 7))), [])

    def test_all_unchanged_or_empty(self):
        self.assertEqual(unchanged_ranges(rows(10)), [(1, 11)])
        self.assertEqual(unchanged_ranges(rows(1)), [])
        self.assertEqual(unchanged_ranges([]), [])

    def test_never_hides_a_changed_row(self):
        for count in range(1, 50):
            changed = set(range(2, count + 1, 9))
            for start, end in unchanged_ranges(rows(count, changed)):
                self.assertTrue(end - start >= 2)
                self.assertTrue(set(range(start, end)).isdisjoint(changed))
