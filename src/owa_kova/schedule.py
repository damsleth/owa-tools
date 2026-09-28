"""Parse Kova's duty list into JSON rows.

`/api/default/GetOpenDuties?pStartDate=<YYYY-MM-DD|''>&pOnlyMine=<bool>`
answers with a JSON string holding an HTML fragment, about two months of
duties from the start date (default: today): `MonthHeader` / `WeekHeader`
divs, then one `div.OpenDuty` per duty. The duty div's classes flag `Me`
(you are on it), `Full`, `Locked` (sign-up closes 48h before) and `History`;
inside it `.Event` / `.Duty` carry the names (their `Title` attribute the
description) and `.Date` the time in one of two shapes:

    ons. 30.09, kl. 18:00 - 21:00
    <b>Fra:</b> fre. 02.10, kl. 18:00<br/><b>Til:</b> søn. 04.10, kl. 15:00

The year is only in the month header above the duty. The crew table holds
other members' names and phone numbers; only your own role is read from it.
"""

import datetime
import html
import re

MONTHS = {name: n for n, name in enumerate(
    'januar februar mars april mai juni juli august september oktober november desember'.split(), 1)}
# ponytail: regex over Kova's server-rendered fragment, not an HTML parser; it
# is one fixed template. Swap for html.parser if Kova ever reshapes it.
_BLOCK_START = re.compile(r'(?=<div class="(?:MonthHeader|OpenDuty))')
_SAME_DAY = re.compile(r'(\d{2})\.(\d{2}), kl\. (\d{2}):(\d{2}) - (\d{2}):(\d{2})')
_SPAN = re.compile(r'Fra:.*?(\d{2})\.(\d{2}), kl\. (\d{2}):(\d{2}).*?Til:.*?(\d{2})\.(\d{2}), kl\. (\d{2}):(\d{2})', re.S)


def _text(fragment):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment or ''))).strip()


def _div(block, cls):
    m = re.search(rf'<div class="{cls}"(?:\s+Title="([^"]*)")?[^>]*>(.*?)</div>', block, re.S)
    return (_text(m.group(2)), html.unescape(m.group(1) or '').strip()) if m else ('', '')


def _attr(block, name):
    m = re.search(rf'\b{name}="([^"]*)"', block)
    return html.unescape(m.group(1)) if m else ''


def _iso(year, month, day, hh, mm):
    return f'{year:04d}-{month:02d}-{day:02d}T{hh:02d}:{mm:02d}'


def parse_times(date_html, year):
    """(start, end) as local ISO strings, or (None, None) for an unknown shape."""
    m = _SPAN.search(date_html)
    if m:
        d1, m1, h1, n1, d2, m2, h2, n2 = map(int, m.groups())
        return _iso(year, m1, d1, h1, n1), _iso(year + (m2 < m1), m2, d2, h2, n2)
    m = _SAME_DAY.search(date_html)
    if m:
        d, mo, h1, n1, h2, n2 = map(int, m.groups())
        start = _iso(year, mo, d, h1, n1)
        if (h2, n2) >= (h1, n1):
            return start, _iso(year, mo, d, h2, n2)
        # Past midnight: ends the next day.
        nxt = datetime.date(year, mo, d) + datetime.timedelta(days=1)
        return start, _iso(nxt.year, nxt.month, nxt.day, h2, n2)
    return None, None


def parse_duties(fragment):
    rows = []
    year = None
    for block in _BLOCK_START.split(fragment or ''):
        if block.startswith('<div class="MonthHeader">'):
            parts = _text(block.split('</div>', 1)[0]).split()
            if len(parts) == 2 and parts[1].isdigit():
                year = int(parts[1])
            continue
        if not block.startswith('<div class="OpenDuty'):
            continue
        classes = _attr(block, 'class').split()
        event, event_info = _div(block, 'Event')
        duty, duty_info = _div(block, 'Duty')
        date_m = re.search(r'<div class="Date"[^>]*>(.*?)</div>', block, re.S)
        date_html = date_m.group(1) if date_m else ''
        start, end = parse_times(date_html, year) if year else (None, None)
        # One cell only: a lazy .*? here spans rows and drags other members'
        # names and numbers into the role.
        role = re.search(r'<td class="Role">((?:(?!</td>).)*)</td>\s*<td class="MyName"', block, re.S)
        rows.append({
            'event': event or _attr(block, 'ReportName'),
            'duty': duty,
            'start': start,
            'end': end,
            'when': _text(date_html),
            'mine': 'Me' in classes,
            'my_role': _text(role.group(1)) if role else None,
            'full': 'Full' in classes,
            'locked': 'Locked' in classes,
            'past': 'History' in classes,
            'event_info': event_info or None,
            'duty_info': duty_info or None,
            'event_ref': _attr(block, 'EventRef') or None,
            'crew_ref': _attr(block, 'CrewRef') or None,
        })
    return rows
