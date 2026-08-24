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
        # Recurrence shape. Consumers that write back need this: editing one
        # Occurrence of a series is a different operation from editing a
        # SingleInstance, and without these fields a caller cannot tell them
        # apart. 'SingleInstance' is the safe default when absent (the webcal
        # path has no equivalent).
        'type': event.get('Type') or 'SingleInstance',
        'seriesMasterId': event.get('SeriesMasterId') or None,
    }


def normalize_events(response):
    """Normalize a calendarView/events collection response."""
    return [normalize_event(e) for e in response.get('value', [])]


def _attendee_brief(att):
    """Flatten one Outlook attendee to {name, address, type, response}."""
    if not isinstance(att, dict):
        return {'name': str(att), 'address': '', 'type': '', 'response': ''}
    email = att.get('EmailAddress') or {}
    return {
        'name': email.get('Name') or email.get('Address') or '',
        'address': email.get('Address') or '',
        'type': att.get('Type') or '',
        'response': (att.get('Status') or {}).get('Response') or '',
    }


def normalize_event_detail(event):
    """`normalize_event` plus the heavier fields the TUI detail pane shows:
    organizer, attendees (each with their response), a plain-text body preview,
    the caller's own response, and whether the caller organizes it.

    Outlook REST PascalCase. Any field absent from a lean query degrades to an
    empty value, so this stays safe even when the heavy fields weren't selected.
    """
    base = normalize_event(event)
    org_email = (event.get('Organizer') or {}).get('EmailAddress') or {}
    base.update({
        'organizer': org_email.get('Name') or org_email.get('Address') or '',
        'attendees': [_attendee_brief(a) for a in (event.get('Attendees') or [])],
        'body': (event.get('BodyPreview') or '').strip(),
        'response': (event.get('ResponseStatus') or {}).get('Response') or '',
        'isOrganizer': bool(event.get('IsOrganizer')),
    })
    return base


def normalize_events_detail(response):
    """Normalize a collection response with the TUI detail fields included."""
    return [normalize_event_detail(e) for e in response.get('value', [])]


# Outlook REST recurrence pattern types keyed by the user-facing --recur
# value. Kept to the pragmatic subset that maps cleanly to a single
# interval: daily / weekly / monthly / yearly. Weekly recurrences need a
# day-of-week anchor, which the caller supplies from the event start date.
_RECUR_PATTERN_TYPES = {
    'daily': 'Daily',
    'weekly': 'Weekly',
    'monthly': 'AbsoluteMonthly',
    'yearly': 'AbsoluteYearly',
}

# weekday() index (Mon=0) -> Outlook REST day-of-week name.
_WEEKDAY_NAMES = [
    'Monday', 'Tuesday', 'Wednesday', 'Thursday',
    'Friday', 'Saturday', 'Sunday',
]


def build_attendees(required=(), optional=()):
    """Build the Outlook REST `Attendees` array from email lists.

    Each entry is `{EmailAddress: {Address}, Type}`. Empty/whitespace
    addresses are skipped. Returns [] when nothing is supplied so callers
    can decide whether to attach the key at all.
    """
    out = []
    for addr in required:
        addr = (addr or '').strip()
        if addr:
            out.append({'EmailAddress': {'Address': addr}, 'Type': 'Required'})
    for addr in optional:
        addr = (addr or '').strip()
        if addr:
            out.append({'EmailAddress': {'Address': addr}, 'Type': 'Optional'})
    return out


def build_recurrence(recur, start_date, interval=1, count=0, until=''):
    """Build the Outlook REST `Recurrence` object, or None if no recur.

    `recur` is one of daily/weekly/monthly/yearly. `start_date` is the
    event's YYYY-MM-DD start, used to anchor the pattern (day-of-week for
    weekly, day-of-month for monthly/yearly) and as the range start.

    Range is `NoEnd` by default, `Numbered` when `count` is given, or
    `EndDate` when `until` (YYYY-MM-DD) is given. `count` and `until` are
    mutually exclusive at the CLI layer.
    """
    if not recur:
        return None
    pattern_type = _RECUR_PATTERN_TYPES.get(recur)
    if pattern_type is None:
        raise ValueError(
            f'unsupported --recur value: {recur} '
            f'(use daily, weekly, monthly, or yearly)'
        )
    dt = datetime.strptime(start_date, '%Y-%m-%d')
    pattern = {'Type': pattern_type, 'Interval': max(1, interval)}
    if pattern_type == 'Weekly':
        pattern['DaysOfWeek'] = [_WEEKDAY_NAMES[dt.weekday()]]
    elif pattern_type == 'AbsoluteMonthly':
        pattern['DayOfMonth'] = dt.day
    elif pattern_type == 'AbsoluteYearly':
        pattern['DayOfMonth'] = dt.day
        pattern['Month'] = dt.month
    if count:
        rng = {'Type': 'Numbered', 'StartDate': start_date,
               'NumberOfOccurrences': count}
    elif until:
        rng = {'Type': 'EndDate', 'StartDate': start_date, 'EndDate': until}
    else:
        rng = {'Type': 'NoEnd', 'StartDate': start_date}
    return {'Pattern': pattern, 'Range': rng}


def build_event_json(
    subject, start_dt, end_dt, tz,
    category='', location='', body_text='', allday=False, showas='',
    categories=(), attendees=(), reminder=None, recurrence=None,
):
    """Build the POST body for creating an Outlook REST event."""
    reminder_on = reminder is not None
    out = {
        'Subject': subject,
        'Start': {'DateTime': start_dt, 'TimeZone': tz},
        'End': {'DateTime': end_dt, 'TimeZone': tz},
        'ShowAs': showas or 'Busy',
        'IsAllDay': bool(allday),
        'IsReminderOn': reminder_on,
    }
    if reminder_on:
        out['ReminderMinutesBeforeStart'] = reminder
    # `category` (single, legacy) and `categories` (repeatable) merge; order
    # preserved, dupes dropped.
    cats = []
    for c in ([category] if category else []) + list(categories):
        if c and c not in cats:
            cats.append(c)
    if cats:
        out['Categories'] = cats
    if location:
        out['Location'] = {'DisplayName': location}
    if body_text:
        out['Body'] = {'ContentType': 'Text', 'Content': body_text}
    if attendees:
        out['Attendees'] = list(attendees)
    if recurrence:
        out['Recurrence'] = recurrence
    return out


def build_patch_json(fields, tz):
    """Build the PATCH body for updating an Outlook REST event.

    `fields` is a dict with any of: subject, categories, location, showas,
    start, end, body, attendees, reminder, recurrence. Only provided keys
    land in the output - that is the load-bearing invariant (commit
    history), so adding keys with empty values to the input is a bug.
    """
    out = {}
    for key, val in fields.items():
        if key == 'subject':
            out['Subject'] = val
        elif key == 'categories':
            out['Categories'] = list(val)
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
        elif key == 'attendees':
            out['Attendees'] = list(val)
        elif key == 'reminder':
            out['ReminderMinutesBeforeStart'] = val
            out['IsReminderOn'] = True
        elif key == 'recurrence':
            out['Recurrence'] = val
    return out
