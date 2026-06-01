"""Human-readable SharePoint formatting for --pretty mode.

Stdout-only; callers decide whether to emit this or raw JSON.
"""
from owa_core.format import pad, truncate


def format_web_pretty(web):
    if not web or not web.get('url'):
        return 'Site not found.'
    lines = [web.get('title') or '']
    lines.append(f"  url: {web.get('url')}")
    if web.get('created'):
        lines.append(f"  created: {web['created']}")
    return '\n'.join(lines)


def format_lists_pretty(lists):
    if not lists:
        return 'No lists found.'
    out = []
    for lst in lists:
        count = lst.get('itemCount')
        count = '?' if count is None else count
        out.append(f"{pad(lst.get('title') or '', 36)}  {str(count):>6}  {lst.get('id') or ''}")
    return '\n'.join(out)


def format_files_pretty(files):
    if not files:
        return 'No files found.'
    out = []
    for f in files:
        length = f.get('length')
        size = '?' if length is None else f'{length}'
        out.append(f"{pad(f.get('name') or '', 44)}  {size:>10}  {f.get('modified') or ''}")
    return '\n'.join(out)


def format_items_pretty(items):
    if not items:
        return 'No items found.'
    out = []
    for item in items:
        title = item.get('Title') or item.get('FileLeafRef') or item.get('Id') or ''
        out.append(str(title))
    return '\n'.join(out)


def format_search_pretty(rows):
    if not rows:
        return 'No results.'
    out = []
    for row in rows:
        title = truncate(row.get('Title') or '', 50)
        out.append(f"{pad(title, 50)}  {row.get('Path') or ''}")
    return '\n'.join(out)
