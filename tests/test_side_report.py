from html.parser import HTMLParser
import unittest

from apptrail.side_report import render_side_html, marked_text
from tests.test_side_diff import change


class ReportParser(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.tags, self.text = [], [], [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag not in ('meta', 'col', 'br'):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            self.errors.append(tag)

    def handle_data(self, data):
        self.text.append(data)


class SideReportTests(unittest.TestCase):
    def test_syntax_words_theme_endings_and_literal_search(self):
        item = change('return 2\r\n', 'return 4\n')
        html = render_side_html(item, {'theme': 'light', 'show_words': True, 'show_endings': True},
                                query='return', active_match={'row': 1, 'side': 'after', 'start': 0, 'end': 6})
        parsed = ReportParser(html)
        self.assertFalse(parsed.errors)
        self.assertFalse(parsed.stack)
        self.assertIn('syn-keyword', html)
        self.assertIn('syn-number word', html)
        self.assertIn('syn-keyword active', html)
        self.assertIn('⟦CRLF⟧', html)
        self.assertIn('⟦LF⟧', html)
        self.assertIn('theme: light', html)
        self.assertIn('#ffffff', html)
        self.assertNotIn('<script', html)
        self.assertIn("default-src 'none'", html)

    def test_expanded_sections_and_context_are_preserved(self):
        before = ''.join(f'line {i}\n' for i in range(40))
        item = change(before, before.replace('line 20\n', 'changed\n'))
        html = render_side_html(item, {'collapse_unchanged': True, 'context_lines': 2}, folded_ranges=[(1, 19)])
        details = [attrs for tag, attrs in ReportParser(html).tags if tag == 'details']
        self.assertEqual(len(details), 2)
        self.assertNotIn('open', details[0])
        self.assertIn('open', details[1])
        self.assertIn('line 0', ''.join(ReportParser(html).text))
        self.assertIn('line 39', ''.join(ReportParser(html).text))
        self.assertIn('context lines: 2', html)

    def test_whitespace_filter_does_not_remove_original_text(self):
        item = change('  value = 1\r\n', 'value=1\n')
        html = render_side_html(item, {'ignore_whitespace': True, 'show_words': False})
        parsed = ReportParser(html)
        classes = [attrs.get('class') for tag, attrs in parsed.tags if tag == 'td']
        self.assertNotIn('code removed', classes)
        self.assertNotIn('code added', classes)
        self.assertIn('  value = 1', ''.join(parsed.text))
        self.assertIn('value=1', ''.join(parsed.text))

    def test_source_path_query_and_markup_are_escaped(self):
        payload = '</td><script>alert("bad")</script>&'
        item = change(payload, payload + '!')
        item['path'] = '<img src=x onerror=bad>.py'
        html = render_side_html(item, {}, query=payload)
        parsed = ReportParser(html)
        self.assertFalse(parsed.errors)
        self.assertFalse(parsed.stack)
        self.assertFalse(any(tag in ('script', 'img', 'iframe') for tag, _ in parsed.tags))
        self.assertIn(payload, ''.join(parsed.text))

    def test_overlapping_spans_and_unicode_reconstruct_exact_text(self):
        content = '😀 café = 42 <x>'
        html = marked_text(content, [(2, 6, 'function'), (9, 11, 'number')], [(9, 11)], [(2, 11)], (2, 11))
        parsed = ReportParser(html)
        self.assertFalse(parsed.errors)
        self.assertFalse(parsed.stack)
        self.assertEqual(''.join(parsed.text), content)

    def test_missing_text_produces_explicit_unavailable_report(self):
        item = change('before', 'after')
        item['before'].pop('text')
        item['before']['text_status'] = 'legacy'
        self.assertIn('older snapshot', render_side_html(item, {}))
