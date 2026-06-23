"""Pretty output for owa-places."""


def format_locations(rows):
    if not rows:
        return '(no locations)'
    headers = ('Name', 'Email', 'Capacity', 'Building', 'Floor')
    data = [
        [
            str(row.get('name') or ''),
            str(row.get('email') or ''),
            '' if row.get('capacity') is None else str(row.get('capacity')),
            str(row.get('building') or ''),
            str(row.get('floor') or ''),
        ]
        for row in rows
    ]
    widths = [len(h) for h in headers]
    for row in data:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = ['  '.join(h.ljust(widths[i]) for i, h in enumerate(headers))]
    lines.append('  '.join('-' * width for width in widths))
    for row in data:
        lines.append('  '.join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
    return '\n'.join(lines)
