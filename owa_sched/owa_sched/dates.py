"""Date / time arithmetic for scheduling.

Pure functions. The CLI builds (start_dt, end_dt) tuples in the
user's preferred Windows timezone string and hands them to Graph
verbatim. Parsing the response back into wall-clock slots is also
pure.
"""
from datetime import date, datetime, timedelta


def today():
    return date.today().isoformat()


def resolve_date(value):
    """Accept YYYY-MM-DD, today, tomorrow, yesterday."""
    v = (value or '').strip().lower()
    if v in ('', 'today'):
        return today()
    if v == 'tomorrow':
        return (date.today() + timedelta(days=1)).isoformat()
    if v == 'yesterday':
        return (date.today() - timedelta(days=1)).isoformat()
    # Validate format
    datetime.strptime(value, '%Y-%m-%d')
    return value


def parse_hhmm(s):
    """'09:00' -> time(9, 0). Strict format."""
    return datetime.strptime(s, '%H:%M').time()


def iso_week_range(week, year):
    """Return (monday, friday) ISO date strings for a given ISO week."""
    monday = date.fromisocalendar(year, week, 1)
    friday = date.fromisocalendar(year, week, 5)
    return monday.isoformat(), friday.isoformat()


def current_year():
    return date.today().isocalendar()[0]


def make_local_iso(date_str, time_str):
    """Combine 'YYYY-MM-DD' + 'HH:MM' into an ISO8601 string with no
    offset. Graph getSchedule accepts a separate timeZone field on
    the start/end objects, so we don't need an offset here."""
    d = datetime.strptime(date_str, '%Y-%m-%d').date()
    t = parse_hhmm(time_str)
    return datetime.combine(d, t).strftime('%Y-%m-%dT%H:%M:%S')


def parse_local_iso(s):
    """Inverse of make_local_iso. Returns naive datetime."""
    # Graph returns "2026-05-04T09:00:00.0000000" sometimes - trim fractional.
    s = (s or '').split('.')[0]
    return datetime.strptime(s, '%Y-%m-%dT%H:%M:%S')


def daterange(start_date, end_date):
    """Inclusive list of YYYY-MM-DD strings between start and end."""
    d0 = datetime.strptime(start_date, '%Y-%m-%d').date()
    d1 = datetime.strptime(end_date, '%Y-%m-%d').date()
    out = []
    cur = d0
    while cur <= d1:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def slots_in_window(start_iso, end_iso, slot_minutes):
    """Generate naive-datetime slot starts of length `slot_minutes`
    that fit entirely within [start_iso, end_iso). Returns a list
    of (slot_start, slot_end) datetime tuples."""
    a = parse_local_iso(start_iso)
    b = parse_local_iso(end_iso)
    out = []
    step = timedelta(minutes=slot_minutes)
    cur = a
    while cur + step <= b:
        out.append((cur, cur + step))
        cur += step
    return out


def overlaps(slot_a, slot_b):
    """Half-open interval overlap test."""
    return slot_a[0] < slot_b[1] and slot_b[0] < slot_a[1]
