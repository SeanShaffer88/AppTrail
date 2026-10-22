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
    def test_ignore_whitespace_indentation_spacing_tabs_and_endings(self):
        item = change('  value = 1\r\n\treturn value\n', 'value=1\n    return  value')
        self.assertTrue(side_by_side(item)['changes'])
        model = side_by_side(item, ignore_whitespace=True)
        self.assertEqual(model['changes'], [])
        self.assertTrue(all(row['ignored_whitespace'] for row in model['rows']))
        self.assertEqual(model['rows'][0]['before'], '  value = 1\r\n')
        self.assertEqual(model['rows'][1]['after_number'], 2)

    def test_ignore_whitespace_keeps_meaningful_edits_and_word_ranges(self):
        item = change('  a = 1\n  b = 2\n  c = 3\n', 'a=1\nb = 4\nc=3\n')
        model = side_by_side(item, True)
        self.assertEqual(model['changes'], [2])
        self.assertEqual(model['rows'][1]['kind'], 'replace')
        self.assertTrue(model['rows'][1]['after_words'])
        self.assertEqual([row['kind'] for row in model['rows']], ['equal', 'replace', 'equal'])

    def test_inserted_blank_lines_preserve_searchable_text_and_original_numbers(self):
        model = side_by_side(change('  keep\nnext\n', '\nkeep\n   \nNEXT\n'), True)
        self.assertEqual(model['changes'], [4])
        self.assertEqual([row['after_number'] for row in model['rows']], [1, 2, 3, 4])
        self.assertEqual(model['rows'][1]['before_number'], 1)
        self.assertTrue(model['rows'][0]['ignored_whitespace'])
        self.assertTrue(model['rows'][2]['ignored_whitespace'])

    def test_whole_file_addition_or_removal_remains_a_change(self):
        self.assertEqual(side_by_side(change(None, '  \n'), True)['changes'], [1])
        self.assertEqual(side_by_side(change('\t\n', None), True)['changes'], [1])

    def test_whitespace_filter_is_textual_including_strings_and_unicode(self):
        self.assertEqual(side_by_side(change('name = "a b"\n', 'name="ab"\n'), True)['changes'], [])
        self.assertEqual(side_by_side(change('α\u00a0= 1\n', 'α=1\n'), True)['changes'], [])

    def test_toggle_model_does_not_mutate_evidence(self):
        import copy
        item = change('  return 1\r\n', 'return 1\n')
        original = copy.deepcopy(item)
        raw = side_by_side(item)
        side_by_side(item, True)
        self.assertEqual(side_by_side(item), raw)
        self.assertEqual(item, original)

    def test_alignment_preserves_each_original_line_once_in_both_modes(self):
        import random
        rng = random.Random(17)
        choices = ['\n', '  \n', '\tx = 1\n', 'x=1\n', 'return 2\n', 'return 3\n']
        for _ in range(100):
            before = ''.join(rng.choices(choices, k=rng.randrange(1, 12)))
            after = ''.join(rng.choices(choices, k=rng.randrange(1, 12)))
            if before == after:
                continue
            for ignore in (False, True):
                rows = side_by_side(change(before, after), ignore)['rows']
                for side, source in (('before', before), ('after', after)):
                    self.assertEqual(''.join(row[side] for row in rows if row[side] is not None), source)
                    self.assertEqual([row[side + '_number'] for row in rows if row[side] is not None],
                                     list(range(1, len(source.splitlines()) + 1)))

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

