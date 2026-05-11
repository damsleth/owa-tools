"""Human-readable event formatting for --pretty mode.

Groups by local date, then sorts events within each day by start time.
Stdout-only; callers decide whether to emit this or raw JSON.
"""
from collections import OrderedDict

from owa_core.format import date_part, pad, time_part


def format_events_pretty(events):
    """Build the multiline human-friendly string. Caller prints it."""
    if not events:
        return 'No events found.'
    by_day = OrderedDict()
    for e in sorted(events, key=lambda x: x.get('start') or ''):
        day = date_part(e.get('start') or '')
        by_day.setdefault(day, []).append(e)
    out = []
    for day in sorted(by_day.keys()):
        out.append(day)
        for e in sorted(by_day[day], key=lambda x: x.get('start') or ''):
            start = time_part(e.get('start') or '')
            end = time_part(e.get('end') or '')
            subj = pad(e.get('subject') or '', 28)
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
