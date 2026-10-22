import hashlib
import unittest

from apptrail.textdiff import side_by_side, side_line, word_changes


def entry(content):
    raw = content.encode('utf-8')
    return {'text': {'content': content, 'encoding': 'utf-8'}, 'text_status': 'captured',
            'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def change(before, after):
    return {'path': 'demo.py', 'status': 'Modified',
            'before': entry(before) if before is not None else None,
            'after': entry(after) if after is not None else None}


class SideDiffTests(unittest.TestCase):
    def words(self, before, after):
        left, right, _ = word_changes(before, after)
        return [before[a:b] for a, b in left], [after[a:b] for a, b in right]

    def test_changed_words_preserve_common_identifiers(self):
        self.assertEqual(self.words('return retry_count + 2', 'return retry_count + 4'), (['2'], ['4']))
        self.assertEqual(self.words('build_name = "stable"', 'build_name = "preview"'), (['stable'], ['preview']))
        self.assertEqual(self.words('retry_count = 2', 'retry_limit = 2'), (['retry_count'], ['retry_limit']))

    def test_insertions_deletions_punctuation_and_whitespace(self):
        self.assertEqual(self.words('call(a)', 'call(a, b)'), ([], [', b']))
        self.assertEqual(self.words('call(a, b)', 'call(a)'), ([', b'], []))
        self.assertEqual(self.words('x == y', 'x != y'), (['='], ['!']))
        self.assertEqual(self.words('  x = 1', '\tx = 1'), (['  '], ['\t']))
        self.assertEqual(self.words('', 'value'), ([], ['value']))

    def test_unicode_ranges_and_multiple_edits(self):
        self.assertEqual(self.words('"😀"; café = 1; return old', '"😀"; café = 2; return new'),
                         (['1', 'old'], ['2', 'new']))

    def test_endings_only_change_uses_markers_and_not_word_ranges(self):
        row = side_by_side(change('same\r\n', 'same\n'))['rows'][0]
        self.assertTrue(row['ending_changed'])
        self.assertEqual(row['before_words'], [])
        self.assertEqual(row['after_words'], [])

    def test_unpaired_rows_do_not_get_word_ranges(self):
        for item in (change(None, 'new\n'), change('old\n', None), change('x\n', 'y\nextra\n')):
            for row in side_by_side(item)['rows']:
                if row['before'] is None or row['after'] is None:
                    self.assertEqual(row['before_words'], [])
                    self.assertEqual(row['after_words'], [])

    def test_bounded_fallback_retains_shared_prefix_and_suffix(self):
        before, after = 'prefix ' + 'x ' * 10000 + 'old suffix', 'prefix ' + 'x ' * 10000 + 'new suffix'
        left, right, cost = word_changes(before, after, budget=1)
        self.assertEqual(cost, 0)
        self.assertEqual([before[a:b] for a, b in left], ['old'])
        self.assertEqual([after[a:b] for a, b in right], ['new'])

    def test_unequal_replacement_preserves_numbers_and_navigation_blocks(self):
        model = side_by_side(change('start\nold\nkeep\nend\n', 'start\nnew\nextra\nkeep\nlast\n'))
        self.assertEqual(model['changes'], [2, 5])
        self.assertEqual([r['before_number'] for r in model['rows']], [1, 2, None, 3, 4])
        self.assertEqual([r['after_number'] for r in model['rows']], [1, 2, 3, 4, 5])
        self.assertEqual(model['rows'][2]['before'], None)

    def test_added_removed_and_empty_files(self):
        for before, after, side in ((None, 'new\n', 'after'), ('old\n', None, 'before')):
            model = side_by_side(change(before, after))
            self.assertEqual(model['changes'], [1])
            self.assertEqual(model['rows'][0][side + '_number'], 1)
        self.assertEqual(side_by_side(change(None, ''))['changes'], [])

    def test_endings_and_missing_newline_are_changes(self):
        model = side_by_side(change('same\r\nlast', 'same\nlast\n'))
        self.assertEqual(model['changes'], [1])
        self.assertIn('⟦CRLF⟧', side_line(1, model['rows'][0]['before'], True))
        self.assertIn('no final newline', side_line(2, 'last', True))
        self.assertEqual(side_line(None, None), '\n')

    def test_legacy_does_not_fabricate_missing_contents(self):
        item = change('old', 'new')
        del item['before']['text']
        item['before']['text_status'] = 'legacy'
        self.assertEqual(side_by_side(item), {'rows': [], 'changes': []})

    def test_encoding_only_change_has_no_line_changes(self):
        self.assertEqual(side_by_side(change('\ufeffsame\n', 'same\n'))['changes'], [])

