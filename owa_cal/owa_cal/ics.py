"""Read-only iCalendar (webcal) source.

Some calendar publishers expose a feed via a `webcal://` URL with a
secret token in the path. There is no OAuth, no Microsoft, no scopes -
just an HTTP GET that returns an RFC 5545 iCalendar text body. This
module is the source-side counterpart to `api.py` for that case.

Scope is deliberately small:
- Single-instance VEVENTs only. No RRULE/RDATE/EXDATE expansion - if
  the feed publishes recurring events as expanded instances we read
  them, otherwise the recurrence is skipped silently.
- UTC and TZID datetimes; all-day from VALUE=DATE.
- VALARM (and any other nested) blocks are skipped via a BEGIN/END
  stack so their properties don't bleed into the parent VEVENT.
- DESCRIPTION/SUMMARY/LOCATION text escapes per RFC 5545 are decoded.
- Attendees, organizer, attachments, X-* extensions: not parsed.

Output of `ics_event_to_normalized` matches the shape produced by
`events.normalize_event` so `format.format_events_pretty` and the
`--pretty` formatter work identically across both sources. The
optional `body` field is populated from DESCRIPTION here.

Stdlib only, per the project ground rule.
"""
from datetime import date, datetime, timezone
from urllib import error, request

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from . import __version__


_FETCH_TIMEOUT = 30
_USER_AGENT = f'owa-cal/{__version__}'


def fetch_ics(url):
    """GET the feed and return the response body decoded as UTF-8.

    Replaces a `webcal://` scheme with `https://` (webcal is just an
    advisory scheme; servers speak HTTP(S)). Raises on transport or
    HTTP errors - the caller turns them into stderr messages.
    """
    if url.startswith('webcal://'):
        url = 'https://' + url[len('webcal://'):]
    elif url.startswith('webcals://'):
        url = 'https://' + url[len('webcals://'):]
    req = request.Request(url, headers={'User-Agent': _USER_AGENT})
    with request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
        raw = resp.read()
    return raw.decode('utf-8', errors='replace')


def _unfold(text):
    """Reverse RFC 5545 §3.1 line folding.

    A continuation line starts with a single SPACE or HTAB; the
    CRLF + that whitespace is removed and the rest joins the previous
    line. We accept LF-only line endings as well, since plenty of
    producers in the wild emit LF.
    """
    out = []
    for raw in text.splitlines():
        if raw and raw[0] in (' ', '\t') and out:
            out[-1] += raw[1:]
        else:
            out.append(raw)
    return out


def _split_params(name_with_params):
    """Split `NAME;P1=V1;P2=V2` into (name, {p1: v1, p2: v2}).

    Parameter values are upper-cased to match RFC 5545's case-insensitive
    handling for the few we care about (VALUE, TZID is left as-is since
    timezone identifiers are case-sensitive in zoneinfo).
    """
    parts = name_with_params.split(';')
    name = parts[0].upper()
    params = {}
    for p in parts[1:]:
        if '=' not in p:
            continue
        k, _, v = p.partition('=')
        k = k.strip().upper()
        v = v.strip().strip('"')
        params[k] = v
    return name, params


def _split_property(line):
    """Split an iCal property line into (name, params, value).

    The first unquoted `:` separates name+params from the value. We
    walk the string instead of using split(':', 1) to tolerate quoted
    parameter values containing a colon (RFC 5545 §3.1.1).
    """
    in_quotes = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == ':' and not in_quotes:
            name, params = _split_params(line[:i])
            return name, params, line[i + 1:]
    return None, None, None


_TEXT_ESCAPES = {'n': '\n', 'N': '\n', '\\': '\\', ',': ',', ';': ';'}


def _unescape_ical_text(s):
    """Decode RFC 5545 TEXT escapes: \\n, \\N, \\\\, \\,, \\;."""
    if '\\' not in s:
        return s
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '\\' and i + 1 < len(s):
            nxt = s[i + 1]
            out.append(_TEXT_ESCAPES.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return ''.join(out)


def _zone_for_tzid(tzid):
    if not tzid or ZoneInfo is None:
        return None
    try:
        return ZoneInfo(tzid)
    except Exception:
        return None


def _parse_ical_datetime(value, params):
    """Parse a DTSTART/DTEND value into (display_str, is_all_day).

    Returns the local-time string in `YYYY-MM-DDTHH:MM:SS` form
    (matching `events.to_local`'s output) for datetime values, or
    `YYYY-MM-DD` for date-only (all-day) values. On parse failure
    returns the raw input so the caller can still surface it.
    """
    if not value:
        return '', False
    if params.get('VALUE') == 'DATE' or (len(value) == 8 and value.isdigit()):
        try:
            d = date(int(value[0:4]), int(value[4:6]), int(value[6:8]))
            return d.strftime('%Y-%m-%d'), True
        except ValueError:
            return value, True
    raw = value
    is_utc = raw.endswith('Z')
    if is_utc:
        raw = raw[:-1]
    try:
        dt = datetime.strptime(raw, '%Y%m%dT%H%M%S')
    except ValueError:
        return value, False
    if is_utc:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        zone = _zone_for_tzid(params.get('TZID'))
        if zone is not None:
            dt = dt.replace(tzinfo=zone)
        else:
            # Floating time or unknown TZID: emit as-is, no conversion.
            return dt.strftime('%Y-%m-%dT%H:%M:%S'), False
    return dt.astimezone().strftime('%Y-%m-%dT%H:%M:%S'), False


def parse_ics(text):
    """Parse iCalendar text into a list of raw VEVENT property dicts.

    Each dict has keys: `summary`, `uid`, `dtstart_value`, `dtstart_params`,
    `dtend_value`, `dtend_params`, `location`, `description`. Missing
    properties land as empty strings / empty dicts.

    VALARM and other nested blocks are skipped via a depth stack: only
    properties read at the VEVENT depth are kept.
    """
    events = []
    current = None
    stack = []
    for line in _unfold(text):
        if not line:
            continue
        name, params, value = _split_property(line)
        if name is None:
            continue
        if name == 'BEGIN':
            block = (value or '').upper()
            stack.append(block)
            # Open a new event the moment we cross into a VEVENT, regardless
            # of how deep it sits inside VCALENDAR / VTIMEZONE / etc.
            # `current is None` keeps us from re-opening if a producer ever
            # ships a VEVENT inside a VEVENT (illegal but seen in the wild).
            if block == 'VEVENT' and current is None:
                current = {
                    'summary': '', 'uid': '',
                    'dtstart_value': '', 'dtstart_params': {},
                    'dtend_value': '', 'dtend_params': {},
                    'location': '', 'description': '',
                }
            continue
        if name == 'END':
            if stack:
                closed = stack.pop()
                if closed == 'VEVENT' and current is not None:
                    events.append(current)
                    current = None
            continue
        # Only collect properties at VEVENT depth: the top of the stack
        # is VEVENT. Inside nested blocks (VALARM, X-*) we discard
        # everything so their DESCRIPTION / SUMMARY don't bleed into the
        # parent event.
        if current is None or not stack or stack[-1] != 'VEVENT':
            continue
        if name == 'SUMMARY':
            current['summary'] = _unescape_ical_text(value or '')
        elif name == 'UID':
            current['uid'] = (value or '').strip()
        elif name == 'DTSTART':
            current['dtstart_value'] = (value or '').strip()
            current['dtstart_params'] = params or {}
        elif name == 'DTEND':
            current['dtend_value'] = (value or '').strip()
            current['dtend_params'] = params or {}
        elif name == 'LOCATION':
            current['location'] = _unescape_ical_text(value or '')
        elif name == 'DESCRIPTION':
            current['description'] = _unescape_ical_text(value or '')
    return events


def ics_event_to_normalized(raw):
    """Map a raw VEVENT dict (from `parse_ics`) into the wire shape
    produced by `events.normalize_event`, with `body` populated from
    DESCRIPTION."""
    start, all_day = _parse_ical_datetime(
        raw.get('dtstart_value', ''), raw.get('dtstart_params', {}),
    )
    end, _ = _parse_ical_datetime(
        raw.get('dtend_value', ''), raw.get('dtend_params', {}),
    )
    return {
        'id': raw.get('uid', ''),
        'subject': raw.get('summary', ''),
        'start': start,
        'end': end,
        'categories': [],
        'location': raw.get('location', ''),
        'showAs': '',
        'isAllDay': all_day,
        'body': raw.get('description', ''),
    }


def fetch_and_normalize(url):
    """Fetch the feed, parse, and return the normalized event list.

    Raises on transport/HTTP errors; the CLI layer catches and renders.
    """
    text = fetch_ics(url)
    return [ics_event_to_normalized(e) for e in parse_ics(text)]


def filter_by_range(events, from_date, to_date):
    """Keep events whose start date falls inside [from_date, to_date].

    Both bounds are `YYYY-MM-DD` strings (inclusive). Events with an
    unparseable start are dropped.
    """
    out = []
    for e in events:
        start = (e.get('start') or '')[:10]
        if not start:
            continue
        if from_date and start < from_date:
            continue
        if to_date and start > to_date:
            continue
        out.append(e)
    return out


def filter_by_subject(events, needle):
    if not needle:
        return events
    needle_l = needle.lower()
    return [
        e for e in events
        if needle_l in (e.get('subject') or '').lower()
    ]


# Re-export so the CLI layer can catch a stable, narrow set.
FetchError = (error.URLError, error.HTTPError, OSError)
