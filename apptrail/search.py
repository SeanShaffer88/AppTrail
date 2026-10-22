"""Literal, single-line search of saved diff rows, excluding UI decorations."""
import re

MAX_MATCHES = 10000


def find_matches(rows, query, match_case=False, limit=MAX_MATCHES):
    if not query:
        return [], False
    pattern = re.compile(re.escape(query), 0 if match_case else re.IGNORECASE)
    matches = []
    for display_row, row in enumerate(rows, 1):
        for side in ('before', 'after'):
            if row[side] is None:
                continue
            content = row[side].rstrip('\r\n')
            for match in pattern.finditer(content):
                if len(matches) == limit:
                    return matches, True
                matches.append({'row': display_row, 'side': side, 'start': match.start(),
                                'end': match.end(), 'line': row[side + '_number']})
    return matches, False
