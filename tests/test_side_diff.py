import hashlib
import unittest

from apptrail.textdiff import side_by_side, side_line


def entry(content):
    raw = content.encode('utf-8')
    return {'text': {'content': content, 'encoding': 'utf-8'}, 'text_status': 'captured',
            'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def change(before, after):
    return {'path': 'demo.py', 'status': 'Modified',
            'before': entry(before) if before is not None else None,
            'after': entry(after) if after is not None else None}


class SideDiffTests(unittest.TestCase):
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

