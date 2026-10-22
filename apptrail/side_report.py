"""Escaped, offline side-by-side HTML with native expandable context."""
from datetime import datetime, timezone
from html import escape
import base64
import hashlib

from . import __version__
from .core import atomic_write
from .folding import unchanged_ranges
from .preferences import diff_options, context_lines
from .search import find_matches
from .syntax import highlight_lines
from .textdiff import side_by_side, build_diff
from .theme import PALETTES
from .report_script import REPORT_SCRIPT


def marked_text(content, syntax, words, matches, active):
    """Sweep span boundaries so overlapping syntax/word/search markup stays valid."""
    events = {}
    for layer, spans in (('syntax', syntax), ('word', [(a, b, 'word') for a, b in words]),
                         ('search', [(a, b, 'active' if (a, b) == active else 'match') for a, b in matches])):
        for start, end, kind in spans:
            events.setdefault(start, []).append((1, layer, kind))
            events.setdefault(end, []).append((0, layer, kind))
    points = sorted({0, len(content), *events})
    state, output = {}, []
    for index, start in enumerate(points[:-1]):
        for opening, layer, kind in sorted(events.get(start, [])):
            if opening:
                state[layer] = kind
            else:
                state.pop(layer, None)
        text = escape(content[start:points[index + 1]], quote=True)
        classes = []
        if 'syntax' in state:
            classes.append('syn-' + state['syntax'])
        classes += [state[layer] for layer in ('word', 'search') if layer in state]
        output.append(f'<span class="{" ".join(classes)}">{text}</span>' if classes else text)
    return ''.join(output)


def render_side_html(change, settings, folded_ranges=None, query='', active_match=None):
    options = diff_options(settings)
    context = context_lines(settings)
    theme = settings.get('theme', 'dark')
    if theme not in ('dark', 'light'):
        theme = 'dark'
    p = PALETTES[theme]
    model = build_diff(change)
    aligned = side_by_side(change, options['ignore_whitespace'])
    rows = aligned['rows']
    change_rows = set(aligned['changes'])
    syntax = {side: highlight_lines(change['path'], ((change.get(side) or {}).get('text') or {}).get('content', ''))[1]
              for side in ('before', 'after')}
    matches, limited = find_matches(rows, query, options['match_case'])
    search = {}
    for match in matches:
        search.setdefault((match['row'], match['side']), []).append((match['start'], match['end']))

    def render_row(index):
        row = rows[index - 1]
        cells = []
        for side in ('before', 'after'):
            number, saved = row[side + '_number'], row[side]
            kind = 'spacer' if saved is None else ('removed' if side == 'before' else 'added') if row['kind'] != 'equal' else 'same'
            content = '' if saved is None else saved.rstrip('\r\n')
            active = ((active_match['start'], active_match['end']) if active_match and
                      active_match['row'] == index and active_match['side'] == side else None)
            code = marked_text(content, syntax[side][number - 1] if number is not None else [],
                               row[side + '_words'] if options['show_words'] else [], search.get((index, side), []), active)
            code = f'<span class="saved-text" data-side="{side.title()}" data-line="{number}">{code}</span>' if saved is not None else code
            if saved is not None and options['show_endings']:
                ending = 'CRLF' if saved.endswith('\r\n') else 'LF' if saved.endswith('\n') else 'CR' if saved.endswith('\r') else 'no final newline'
                marker_class = 'word' if options['show_words'] and row['ending_changed'] else 'ending'
                code += f'<span class="{marker_class}">  ⟦{ending}⟧</span>'
            cells.append(f'<td class="number {kind}">{number if number is not None else ""}</td><td class="code {kind}">{code}</td>')
        anchor = f' id="change-{index}" data-change="{index}"' if index in change_rows else ''
        return f'<tr{anchor}>' + ''.join(cells) + '</tr>'

    def table(start, end):
        return '<table><colgroup><col class="gutter"><col><col class="gutter"><col></colgroup><tbody>' + ''.join(render_row(i) for i in range(start, end)) + '</tbody></table>'

    ranges = unchanged_ranges(rows, context) if options['collapse_unchanged'] else []
    closed = set(ranges if folded_ranges is None else (tuple(pair) for pair in folded_ranges))
    sections, cursor = [], 1
    for start, end in ranges:
        if cursor < start:
            sections.append(table(cursor, start))
        opened = '' if (start, end) in closed else ' open'
        sections.append(f'<details{opened}><summary>{end - start} unchanged rows · expand/collapse</summary>{table(start, end)}</details>')
        cursor = end
    if cursor <= len(rows):
        sections.append(table(cursor, len(rows) + 1))
    width = max([80] + [len((row[side] or '').expandtabs(4).rstrip('\r\n')) + (28 if options['show_endings'] else 0)
                        for row in rows for side in ('before', 'after')]) * 2 + 14
    settings_text = ', '.join(f'{key.replace("_", " ")}: {"on" if value else "off"}' for key, value in options.items())
    settings_text += f', context lines: {context}, theme: {theme}'
    syntax_css = ''.join(f'.syn-{kind}{{color:{p[kind]}}}' for kind in ('comment', 'keyword', 'string', 'number', 'function', 'type', 'operator'))
    evidence = ''.join(f'<p><b>{side.title()}</b>: {escape(model[side + "_summary"])}<br>SHA-256: {escape(str((change.get(side) or {}).get("sha256") or "Not captured"))}</p>' for side in ('before', 'after'))
    search_note = (f'<p>Search: {escape(query, quote=True)} · {len(matches)}{"+" if limited else ""} matches'
                   + (' · active occurrence highlighted' if active_match and matches else '') + '.</p>') if query else ''
    body = ''.join(sections) or '<p>' + escape(model['message']) + '</p>'
    script_hash = base64.b64encode(hashlib.sha256(REPORT_SCRIPT.encode('utf-8')).digest()).decode('ascii')
    initial_match = next((i for i, match in enumerate(matches) if active_match and
                         all(match[key] == active_match[key] for key in ('row', 'side', 'start', 'end'))), 0)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>AppTrail · {escape(change['path'], quote=True)}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:{p['bg']};color:{p['fg']};font:14px/1.5 'Segoe UI',sans-serif}}main{{padding:24px}}h1{{overflow-wrap:anywhere}}p{{overflow-wrap:anywhere}}
.viewport{{overflow:auto;border:1px solid {p['panel']};background:{p['field']}}}table{{border-collapse:collapse;width:100%;table-layout:fixed;min-width:{width}ch;font:13px/1.5 Consolas,monospace}}.gutter{{width:6ch}}td{{vertical-align:top}}.code{{white-space:pre;tab-size:4;padding:0 8px}}.number{{color:{p['muted']};text-align:right;padding:0 8px;user-select:none}}.head{{display:flex;justify-content:space-around;background:{p['panel']};padding:8px;font-weight:bold}}
.added{{background:{p['add']}}}.removed{{background:{p['remove']}}}.spacer{{background:{p['spacer']}}}.added .word{{background:{p['word_add']}}}.removed .word{{background:{p['word_remove']}}}.ending{{color:{p['muted']}}}
{syntax_css}.code .match{{background:{p['search']}}}.active{{background:{p['search_active']}!important;color:{p['search_text']}!important}}summary{{cursor:pointer;background:{p['panel']};padding:8px}}footer{{margin-top:20px;color:{p['muted']}}}
.review-tools{{position:sticky;top:0;z-index:2;background:{p['panel']};padding:12px;border:1px solid {p['muted']}}}.review-tools[hidden]{{display:none}}.tool-row{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:4px 0}}input,button{{background:{p['field']};color:{p['fg']};border:1px solid {p['muted']};padding:6px;font:inherit}}button{{cursor:pointer}}button:disabled{{opacity:.5;cursor:default}}input[type=search]{{min-width:160px;flex:1}}.code .live-hit{{background:{p['search']};color:inherit}}.code .live-current{{background:{p['search_active']}!important;color:{p['search_text']}!important}}.review-current{{outline:2px solid {p['accent']};outline-offset:-2px}}[role=status]{{color:{p['muted']}}}
@media print{{.viewport{{overflow:visible}}table{{min-width:0}}.code{{white-space:pre-wrap;overflow-wrap:anywhere}}}}
</style></head><body><main><h1>{escape(change['status'])} · {escape(change['path'])}</h1>
<p>Side-by-side saved text · AppTrail {__version__} · {datetime.now(timezone.utc).isoformat(timespec='seconds')}</p>
<p>{escape(settings_text)}</p>{evidence}{search_note}
<section id="review-controls" class="review-tools" hidden data-initial-match="{initial_match}" aria-label="Review controls">
<div class="tool-row"><button type="button" id="previous-change">◀ Previous change</button><button type="button" id="next-change">Next change ▶</button><span id="change-status" role="status" aria-live="polite"></span><button type="button" id="expand-all">Expand all unchanged</button><button type="button" id="collapse-all">Collapse all unchanged</button><span id="section-status" role="status" aria-live="polite"></span></div>
<div class="tool-row"><label for="find-text">Find:</label><input type="search" id="find-text" value="{escape(query, quote=True)}" aria-label="Find in both snapshots"><label><input type="checkbox" id="find-case"{' checked' if options['match_case'] else ''}>Match case</label><button type="button" id="previous-match">◀ Match</button><button type="button" id="next-match">Match ▶</button><button type="button" id="clear-find">Clear</button></div>
<div id="find-status" role="status" aria-live="polite"></div><small>F3 / Shift+F3: matches · F7 / Shift+F7: changes · Enter / Shift+Enter in Find: matches</small></section>
<noscript><p>JavaScript is disabled. Use browser Find and expand sections manually; report contents and colors remain available.</p></noscript>
<div class="head"><span>Before</span><span>After</span></div><div class="viewport">{body}</div>
<footer>Saved evidence only. Display settings may suppress whitespace-only changes; whitespace can matter in strings and indentation-sensitive code.
Expandable sections contain the full saved text, including code initially hidden. Review this report before sharing. Review controls use one embedded script; no external assets or network requests are used.</footer></main><script>{REPORT_SCRIPT}</script></body></html>'''


def export_side_report(change, settings, path, **kwargs):
    atomic_write(path, render_side_html(change, settings, **kwargs))
