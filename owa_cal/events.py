"""Event JSON shaping: normalize API responses, build POST/PATCH bodies.

owa-cal talks to the Outlook REST API v2.0, which returns PascalCase.
We normalize into lowercase-key shapes on read and emit PascalCase on
write. See `auth.py` for why Microsoft Graph is not an option on the
owa-piggy auth path.
"""
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8: keep the stdlib-only fallback below.
    ZoneInfo = None

# Windows timezone names -> IANA names for accurate stdlib zoneinfo
# conversion where available. Outlook REST returns these names in the
# TimeZone field.
WINDOWS_TZ_TO_IANA = {
    'UTC': 'UTC',
    'W. Europe Standard Time': 'Europe/Berlin',
    'Romance Standard Time': 'Europe/Paris',
    'Central European Standard Time': 'Europe/Warsaw',
    'Central Europe Standard Time': 'Europe/Budapest',
    'E. Europe Standard Time': 'Europe/Bucharest',
    'FLE Standard Time': 'Europe/Helsinki',
    'GTB Standard Time': 'Europe/Athens',
    'GMT Standard Time': 'Europe/London',
    'Eastern Standard Time': 'America/New_York',
    'Pacific Standard Time': 'America/Los_Angeles',
    'Mountain Standard Time': 'America/Denver',
    'Central Standard Time': 'America/Chicago',
}

# Windows timezone names -> UTC offset hours (winter baseline). Used only
# when zoneinfo is unavailable.
TZ_OFFSETS = {
    'UTC': 0,
    'W. Europe Standard Time': 1, 'Romance Standard Time': 1,
    'Central European Standard Time': 1, 'Central Europe Standard Time': 1,
    'E. Europe Standard Time': 2, 'FLE Standard Time': 2,
    'GTB Standard Time': 2, 'Eastern Standard Time': -5,
    'Pacific Standard Time': -8, 'Mountain Standard Time': -7,
    'Central Standard Time': -6, 'GMT Standard Time': 0,
}

EUROPEAN_TZ_NAMES = {
    'W. Europe Standard Time',
    'Romance Standard Time',
    'Central European Standard Time',
    'Central Europe Standard Time',
    'E. Europe Standard Time',
    'FLE Standard Time',
    'GTB Standard Time',
    'GMT Standard Time',
}

US_TZ_NAMES = {
    'Eastern Standard Time',
    'Pacific Standard Time',
    'Mountain Standard Time',
    'Central Standard Time',
}


def _last_sunday(year, month):
    return max(
        d for d in range(25, 32)
        if datetime(year, month, d).weekday() == 6
    )


def _nth_weekday(year, month, weekday, n):
    seen = 0
    for day in range(1, 32):
        try:
            if datetime(year, month, day).weekday() == weekday:
                seen += 1
                if seen == n:
                    return day
        except ValueError:
            break
    return 0


def is_dst_europe(dt, base_offset=1):
    """DST active for a European zone on the given naive datetime.

    EU DST starts at 01:00 UTC on the last Sunday of March and ends at
    01:00 UTC on the last Sunday of October. `base_offset` is the
    standard-time UTC offset for the zone.
    """
    if dt.month < 3 or dt.month > 10:
        return False
    if 3 < dt.month < 10:
        return True
    last_sunday = _last_sunday(dt.year, dt.month)
    if dt.month == 3:
        return dt.day > last_sunday or (
            dt.day == last_sunday and dt.hour >= base_offset + 1
        )
    return dt.day < last_sunday or (
        dt.day == last_sunday and dt.hour < base_offset + 2
    )


def _is_dst_us(dt):
    """US DST: second Sunday in March through first Sunday in November."""
    if dt.month < 3 or dt.month > 11:
        return False
    if 3 < dt.month < 11:
        return True
    if dt.month == 3:
        start_day = _nth_weekday(dt.year, 3, 6, 2)
        return dt.day > start_day or (dt.day == start_day and dt.hour >= 2)
    end_day = _nth_weekday(dt.year, 11, 6, 1)
    return dt.day < end_day or (dt.day == end_day and dt.hour < 2)


def _parse_outlook_datetime(dt_str):
    clean = dt_str.strip()
    if clean.endswith('Z'):
        clean = clean[:-1] + '+00:00'
    if '.' in clean:
        prefix, rest = clean.split('.', 1)
        digits = []
        suffix_at = len(rest)
        for i, ch in enumerate(rest):
            if ch.isdigit():
                digits.append(ch)
            else:
                suffix_at = i
                break
        frac = ''.join(digits)[:6]
        suffix = rest[suffix_at:]
        clean = f'{prefix}.{frac}{suffix}' if frac else f'{prefix}{suffix}'
    return datetime.fromisoformat(clean)


def _windows_zoneinfo(tz_name):
    if ZoneInfo is None:
        return None
    iana = WINDOWS_TZ_TO_IANA.get(tz_name)
    if not iana:
        return None
    try:
        return ZoneInfo(iana)
    except Exception:
        return None


def _fallback_timezone(tz_name, dt):
    if tz_name not in TZ_OFFSETS:
        return timezone.utc
    base = TZ_OFFSETS[tz_name]
    dst = 0
    if tz_name in EUROPEAN_TZ_NAMES and is_dst_europe(dt, base):
        dst = 1
    elif tz_name in US_TZ_NAMES and _is_dst_us(dt):
        dst = 1
    return timezone(timedelta(hours=base + dst))


def to_local(dt_str, tz_name=''):
    """Convert an Outlook datetime string to local time.

    - Drops sub-second precision and trailing Z.
    - If the string already carries an offset, trusts it.
    - If tz_name matches a known Windows zone, interprets the naive
      datetime in that zone (with European DST).
    - Otherwise assumes UTC (Outlook REST default).
    """
    if not dt_str:
        return dt_str
    try:
        dt = _parse_outlook_datetime(dt_str)
    except ValueError:
        return dt_str
    # Build an aware datetime, then let datetime.astimezone() read the
    # host's real local TZ (including per-instant DST). The previous
    # implementation used time.altzone whenever the host zone observed
    # DST at all, which produced summer offsets for winter events.
    if dt.tzinfo is None:
        tz = _windows_zoneinfo(tz_name) or _fallback_timezone(tz_name, dt)
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone().strftime('%Y-%m-%dT%H:%M:%S')


def normalize_event(event):
    """Flatten an Outlook REST event (PascalCase) into owa-cal's wire shape.

    The wire shape is also produced by the webcal/iCal path in `ics.py`,
    which populates the optional `body` field from DESCRIPTION. Outlook
    REST `calendarView` does not return Body by default and the field is
    omitted here to keep the JSON compact.
    """
    s = event.get('Start') or {}
    en = event.get('End') or {}
    loc = event.get('Location') or {}
    return {
        'id': event.get('Id'),
        'subject': event.get('Subject'),
        'start': to_local(s.get('DateTime') or '', s.get('TimeZone') or ''),
        'end': to_local(en.get('DateTime') or '', en.get('TimeZone') or ''),
        'categories': event.get('Categories') or [],
        'location': loc.get('DisplayName') or '',
        'showAs': event.get('ShowAs') or '',
        'isAllDay': event.get('IsAllDay') or False,
    }


def normalize_events(response):
    """Normalize a calendarView/events collection response."""
    return [normalize_event(e) for e in response.get('value', [])]


def build_event_json(
    subject, start_dt, end_dt, tz,
    category='', location='', body_text='', allday=False, showas='',
):
    """Build the POST body for creating an Outlook REST event."""
    out = {
        'Subject': subject,
        'Start': {'DateTime': start_dt, 'TimeZone': tz},
        'End': {'DateTime': end_dt, 'TimeZone': tz},
        'ShowAs': showas or 'Busy',
        'IsAllDay': bool(allday),
        'IsReminderOn': False,
    }
    if category:
        out['Categories'] = [category]
    if location:
        out['Location'] = {'DisplayName': location}
    if body_text:
        out['Body'] = {'ContentType': 'Text', 'Content': body_text}
    return out


def build_patch_json(fields, tz):
    """Build the PATCH body for updating an Outlook REST event.

    `fields` is a dict with any of: subject, category, location, showas,
    start, end, body. Only provided keys land in the output - that is
    the load-bearing invariant (commit history), so adding keys with
    empty values to the input is a bug.
    """
    out = {}
    for key, val in fields.items():
        if key == 'subject':
            out['Subject'] = val
        elif key == 'category':
            out['Categories'] = [val]
        elif key == 'location':
            out['Location'] = {'DisplayName': val}
        elif key == 'showas':
            out['ShowAs'] = val
        elif key == 'start':
            out['Start'] = {'DateTime': val, 'TimeZone': tz}
        elif key == 'end':
            out['End'] = {'DateTime': val, 'TimeZone': tz}
        elif key == 'body':
            out['Body'] = {'ContentType': 'Text', 'Content': val}
    return out
