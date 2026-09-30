"""--pretty rendering for owa-gdrive."""


def _size(n):
    if n is None:
        return '-'
    for unit in ('B', 'K', 'M', 'G'):
        if n < 1024 or unit == 'G':
            return f'{n:.0f}{unit}' if unit == 'B' else f'{n:.1f}{unit}'
        n /= 1024
    return str(n)


def format_files_pretty(rows):
    if not rows:
        return '(no files)'
    lines = []
    for f in rows:
        name = f['name'] + ('/' if f['kind'] == 'folder' else '')
        lines.append(f"{f['modified'][:16].replace('T', ' '):16}  {_size(f['size']):>7}  {name}")
        lines.append(f"    {f['id']}")
    return '\n'.join(lines)


def format_file_pretty(f):
    lines = [
        f"Name:     {f['name']}",
        f"Kind:     {f['kind']}  ({f['mime_type']})",
        f"Size:     {_size(f['size'])}",
        f"Modified: {f['modified']}",
    ]
    if f.get('owners'):
        lines.append(f"Owners:   {', '.join(f['owners'])}")
    if f.get('parents'):
        lines.append(f"Parents:  {', '.join(f['parents'])}")
    lines.append(f"Link:     {f['web_view_link']}")
    lines.append(f"Id:       {f['id']}")
    return '\n'.join(lines)
