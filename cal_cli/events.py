"""Event JSON shaping: normalize API responses, build POST/PATCH bodies.

The Outlook REST API (v2.0) uses PascalCase; Microsoft Graph uses
camelCase. We prefer Outlook REST because it is what the refresh token
actually lands on, but the helpers here stay case-agnostic so a future
Graph switch does not require a rewrite.
"""
import time
from datetime import datetime, timedelta, timezone

# Windows timezone names -> UTC offset hours (winter baseline). DST is
# applied on top for European zones via is_dst_europe(). Outlook REST
# returns these names in the TimeZone field.
TZ_OFFSETS = {
    'UTC': 0,
    'W. Europe Standard Time': 1, 'Romance Standard Time': 1,
    'Central European Standard Time': 1, 'Central Europe Standard Time': 1,
    'E. Europe Standard Time': 2, 'FLE Standard Time': 2,
    'GTB Standard Time': 2, 'Eastern Standard Time': -5,
    'Pacific Standard Time': -8, 'Mountain Standard Time': -7,
    'Central Standard Time': -6, 'GMT Standard Time': 0,
}


def _local_tz():
    """Local timezone as a fixed offset from stdlib time module."""
    offset = -time.timezone if time.daylight == 0 else -time.altzone
    return timezone(timedelta(seconds=offset))


def is_dst_europe(dt):
    """DST active for a European zone on the given naive datetime.

    Last Sunday of March through last Sunday of October. Good enough for
    the tz names we actually see from Outlook; we do not carry pytz.
    """
    if dt.month < 3 or dt.month > 10:
        return False
    if 3 < dt.month < 10:
        return True
    last_sunday = max(
        d for d in range(25, 32)
        if datetime(dt.year, dt.month, d).weekday() == 6
    )
    if dt.month == 3:
        return dt.day >= last_sunday
    return dt.day < last_sunday


def to_local(dt_str, tz_name=''):
    """Convert an Outlook/Graph datetime string to local time.

    - Drops sub-second precision and trailing Z.
    - If the string already carries an offset, trusts it.
    - If tz_name matches a known Windows zone, interprets the naive
      datetime in that zone (with European DST).
    - Otherwise assumes UTC (Outlook REST default).
    """
    if not dt_str:
        return dt_str
    clean = dt_str.split('.')[0].replace('Z', '')
    try:
        dt = datetime.fromisoformat(clean)
    except ValueError:
        return dt_str
    local_tz = _local_tz()
    if dt.tzinfo is not None:
        return dt.astimezone(local_tz).strftime('%Y-%m-%dT%H:%M:%S')
    if tz_name in TZ_OFFSETS:
        base = TZ_OFFSETS[tz_name]
        dst = 1 if base != 0 and -1 <= base <= 3 and is_dst_europe(dt) else 0
        source = timezone(timedelta(hours=base + dst))
        dt = dt.replace(tzinfo=source)
        return dt.astimezone(local_tz).strftime('%Y-%m-%dT%H:%M:%S')
    dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(local_tz).strftime('%Y-%m-%dT%H:%M:%S')


def normalize_event(event):
    """Collapse Outlook PascalCase / Graph camelCase to a single shape."""
    s = event.get('Start') or event.get('start') or {}
    en = event.get('End') or event.get('end') or {}
    loc = event.get('Location') or event.get('location') or {}
    s_tz = s.get('TimeZone') or s.get('timeZone') or ''
    e_tz = en.get('TimeZone') or en.get('timeZone') or ''
    return {
        'id': event.get('Id') or event.get('id'),
        'subject': event.get('Subject') or event.get('subject'),
        'start': to_local(s.get('DateTime') or s.get('dateTime') or '', s_tz),
        'end': to_local(en.get('DateTime') or en.get('dateTime') or '', e_tz),
        'categories': event.get('Categories') or event.get('categories') or [],
        'location': loc.get('DisplayName') or loc.get('displayName') or '',
        'showAs': event.get('ShowAs') or event.get('showAs') or '',
        'isAllDay': event.get('IsAllDay') or event.get('isAllDay') or False,
    }


def normalize_events(response):
    """Normalize a calendarView/events collection response."""
    return [normalize_event(e) for e in response.get('value', [])]


def build_event_json(
    subject, start_dt, end_dt, tz,
    category='', location='', body_text='', allday=False, showas='',
    api_case='pascal',
):
    """Build the POST body for creating an event. Honors api_case so we
    can talk to either Outlook REST (pascal) or Graph (camel) cleanly."""
    if api_case == 'camel':
        out = {
            'subject': subject,
            'start': {'dateTime': start_dt, 'timeZone': tz},
            'end': {'dateTime': end_dt, 'timeZone': tz},
            'showAs': showas or 'busy',
            'isAllDay': bool(allday),
            'isReminderOn': False,
        }
        if category:
            out['categories'] = [category]
        if location:
            out['location'] = {'displayName': location}
        if body_text:
            out['body'] = {'contentType': 'text', 'content': body_text}
        return out
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


def build_patch_json(fields, tz, api_case='pascal'):
    """Build the PATCH body for updating an event.

    `fields` is a dict with any of: subject, category, location, showas,
    start, end, body. Only provided keys land in the output - that is
    the load-bearing invariant (commit history), so adding keys with
    empty values to the input is a bug.
    """
    camel = api_case == 'camel'
    out = {}
    for key, val in fields.items():
        if key == 'subject':
            out['subject' if camel else 'Subject'] = val
        elif key == 'category':
            out['categories' if camel else 'Categories'] = [val]
        elif key == 'location':
            if camel:
                out['location'] = {'displayName': val}
            else:
                out['Location'] = {'DisplayName': val}
        elif key == 'showas':
            out['showAs' if camel else 'ShowAs'] = val
        elif key == 'start':
            if camel:
                out['start'] = {'dateTime': val, 'timeZone': tz}
            else:
                out['Start'] = {'DateTime': val, 'TimeZone': tz}
        elif key == 'end':
            if camel:
                out['end'] = {'dateTime': val, 'timeZone': tz}
            else:
                out['End'] = {'DateTime': val, 'TimeZone': tz}
        elif key == 'body':
            if camel:
                out['body'] = {'contentType': 'text', 'content': val}
            else:
                out['Body'] = {'ContentType': 'Text', 'Content': val}
    return out
