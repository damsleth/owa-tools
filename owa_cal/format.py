"""Human-readable event formatting for --pretty mode.

Groups by local date, then sorts events within each day by start time.
Stdout-only; callers decide whether to emit this or raw JSON.
"""
from collections import OrderedDict


def _date_part(iso):
    return iso.split('T')[0] if iso else ''


def _time_part(iso):
    if not iso or 'T' not in iso:
        return ''
    return ':'.join(iso.split('T')[1].split(':')[:2])


def _pad(s, n):
    s = str(s)
    return s + ' ' * (n - len(s)) if len(s) < n else s


def format_events_pretty(events):
    """Build the multiline human-friendly string. Caller prints it."""
    if not events:
        return 'No events found.'
    by_day = OrderedDict()
    for e in sorted(events, key=lambda x: x.get('start') or ''):
        day = _date_part(e.get('start') or '')
        by_day.setdefault(day, []).append(e)
    out = []
    for day in sorted(by_day.keys()):
        out.append(day)
        for e in sorted(by_day[day], key=lambda x: x.get('start') or ''):
            start = _time_part(e.get('start') or '')
            end = _time_part(e.get('end') or '')
            subj = _pad(e.get('subject') or '', 28)
            loc = e.get('location') or ''
            cats = e.get('categories') or []
            loc_str = f'{loc}  ' if loc else ''
            cat_str = f'[{", ".join(cats)}]' if cats else ''
            out.append(f'  {start}-{end}  {subj}{loc_str}{cat_str}')
            body = (e.get('body') or '').strip()
            if body:
                for line in body.splitlines():
                    if line.strip():
                        out.append(f'      {line}')
        out.append('')
    return '\n'.join(out)
