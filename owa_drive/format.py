"""Human-readable rendering for `--pretty`."""


def _human_size(n):
    if n is None:
        return '-'
    try:
        n = int(n)
    except (TypeError, ValueError):
        return '-'
    units = ('B', 'K', 'M', 'G', 'T')
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024
        i += 1
    if i == 0:
        return f'{int(f)}{units[i]}'
    return f'{f:.1f}{units[i]}'


def _truncate(s, n):
    s = s or ''
    if len(s) <= n:
        return s
    return s[: n - 1] + '...'


def format_items_pretty(items):
    if not items:
        return '(empty)'
    rows = [('kind', 'size', 'modified', 'name')]
    for it in items:
        kind = 'd' if it.get('kind') == 'folder' else 'f'
        size = _human_size(it.get('size'))
        modified = (it.get('lastModified') or '')[:19].replace('T', ' ')
        rows.append((kind, size, modified, _truncate(it.get('name'), 80)))
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    out = []
    for r in rows:
        out.append('  '.join(c.ljust(w) for c, w in zip(r, widths)).rstrip())
    return '\n'.join(out)


def format_item_pretty(it):
    if not it:
        return '(no item)'
    lines = [f"{it.get('name') or '(no name)'} [{it.get('kind')}]"]
    if it.get('size') is not None:
        lines.append(f"  size:     {_human_size(it.get('size'))}")
    if it.get('mimeType'):
        lines.append(f"  type:     {it.get('mimeType')}")
    if it.get('lastModified'):
        lines.append(f"  modified: {it.get('lastModified')}")
    if it.get('parentPath'):
        lines.append(f"  parent:   {it.get('parentPath')}")
    if it.get('webUrl'):
        lines.append(f"  url:      {it.get('webUrl')}")
    if it.get('id'):
        lines.append(f"  id:       {it.get('id')}")
    return '\n'.join(lines)
