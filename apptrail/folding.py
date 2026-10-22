"""Locate unchanged row ranges while retaining context around edits."""


def unchanged_ranges(rows, context=3):
    """Return one-based, end-exclusive ranges with at least two hidden rows."""
    ranges = []
    index = 0
    while index < len(rows):
        if rows[index]['kind'] != 'equal':
            index += 1
            continue
        start = index
        while index < len(rows) and rows[index]['kind'] == 'equal':
            index += 1
        first = start + (context if start else 0)
        last = index - (context if index < len(rows) else 0)
        if last - first >= 2:
            ranges.append((first + 1, last + 1))
    return ranges
