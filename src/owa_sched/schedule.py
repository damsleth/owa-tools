"""Pure-function helpers for getSchedule responses and slot finding.

Graph response shape (one element per scheduleId):
    {
      "scheduleId": "alice@x.com",
      "availabilityView": "0220...",   # one digit per interval
      "scheduleItems": [
        {"status":"busy",
         "start":{"dateTime":"...","timeZone":"..."},
         "end":{"dateTime":"...","timeZone":"..."},
         "subject":"..."},
        ...
      ],
      "workingHours": {...}
    }
"""
from datetime import datetime, time

from owa_core.errors import ConflictError, UsageError
from owa_core.timezones import resolve_timezone

from .dates import overlaps, slots_in_window

# Graph daysOfWeek strings -> Python weekday() index (Mon=0 .. Sun=6).
_WEEKDAY_INDEX = {
    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
    'friday': 4, 'saturday': 5, 'sunday': 6,
}


def _parse_working_hours(raw):
    """Return JSON-safe working hours, retaining the upstream timezone."""
    if not isinstance(raw, dict):
        return None
    days = {
        _WEEKDAY_INDEX[d.lower()]
        for d in (raw.get('daysOfWeek') or [])
        if isinstance(d, str) and d.lower() in _WEEKDAY_INDEX
    }
    start = _parse_time_of_day(raw.get('startTime'))
    end = _parse_time_of_day(raw.get('endTime'))
    if not days or start is None or end is None:
        return None
    return {'days': sorted(days), 'start': start.isoformat(), 'end': end.isoformat(),
            'timeZone': raw.get('timeZone') or None}


def _parse_time_of_day(value):
    """Parse a Graph Edm.TimeOfDay ('08:00:00.0000000') to a time(). Returns
    None on anything unparseable."""
    if not isinstance(value, str) or not value:
        return None
    hhmm = value.split('.')[0]  # drop fractional seconds
    parts = hhmm.split(':')
    if len(parts) < 2:
        return None
    try:
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, TypeError):
        return None


def normalize_attendee(entry):
    """Project a Graph schedule entry into a flat shape."""
    out = {
        'email': entry.get('scheduleId') or '',
        'availabilityView': entry.get('availabilityView') or '',
        'busy': [],
        'workingHours': _parse_working_hours(entry.get('workingHours')),
        'error': None,
    }
    if entry.get('error'):
        # Graph reports unresolvable mailboxes etc. as a per-entry error
        err = entry['error']
        if isinstance(err, dict):
            out['error'] = err.get('message') or str(err)
        else:
            out['error'] = str(err)
        return out
    if entry.get('workingHours') is not None and out['workingHours'] is None:
        out['error'] = 'unparseable working hours'
    items = entry.get('scheduleItems') or []
    for it in items:
        status = (it.get('status') or '').lower()
        if status in ('free', 'workingelsewhere'):
            continue
        start = (it.get('start') or {}).get('dateTime') or ''
        end = (it.get('end') or {}).get('dateTime') or ''
        out['busy'].append({
            'start': start,
            'end': end,
            'startTimeZone': (it.get('start') or {}).get('timeZone'),
            'endTimeZone': (it.get('end') or {}).get('timeZone'),
            'status': status,
            'subject': it.get('subject') or '',
        })
    return out


def _working_zone(raw, fallback):
    if not raw:
        return fallback
    if isinstance(raw, dict):
        if raw.get('@odata.type', '').endswith('customTimeZone') or 'bias' in raw:
            raise UsageError('custom working-hours timezone is unsupported; use find-time --server')
        raw = raw.get('name')
    return resolve_timezone(raw)


def _slot_within_working_hours(slot, working_hours_list, window_zone):
    for wh in working_hours_list:
        zone = _working_zone(wh.get('timeZone'), window_zone)
        start = slot[0].replace(tzinfo=window_zone).astimezone(zone)
        end = slot[1].replace(tzinfo=window_zone).astimezone(zone)
        wh_start = _parse_time_of_day(wh['start'])
        wh_end = _parse_time_of_day(wh['end'])
        if wh_start is None or wh_end is None or wh_start >= wh_end:
            raise ConflictError('cannot determine availability from invalid working hours')
        if start.weekday() not in wh['days']:
            return False
        lower = datetime.combine(start.date(), wh_start, zone)
        upper = datetime.combine(start.date(), wh_end, zone)
        if start < lower or end > upper:
            return False
    return True


def _busy_datetime(value, source_zone, window_zone):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_working_zone(source_zone, window_zone))
    return parsed.astimezone(window_zone).replace(tzinfo=None)


def find_open_slots(attendees, window_start, window_end, slot_minutes, *, timezone="UTC"):
    """Return slot tuples (start_iso, end_iso) within
    [window_start, window_end) where every attendee is free and
    (when advertised) inside every attendee's own workingHours.

    `attendees` is a list of normalized dicts (output of
    normalize_attendee). `window_start` / `window_end` are ISO local
    strings. Slot times are returned as ISO local strings to match.
    """
    window_zone = resolve_timezone(timezone)
    busy_dts = []
    working_hours_list = []
    for a in attendees:
        if a.get('error'):
            raise ConflictError(f"availability unknown for {a.get('email') or 'attendee'}: {a['error']}")
        for b in a.get('busy') or []:
            try:
                start = _busy_datetime(b['start'], b.get('startTimeZone'), window_zone)
                end = _busy_datetime(b['end'], b.get('endTimeZone'), window_zone)
                if end <= start:
                    raise ValueError('non-positive busy interval')
                busy_dts.append((start, end))
            except (ValueError, KeyError, TypeError) as exc:
                raise ConflictError('cannot determine availability from invalid busy interval') from exc
        wh = a.get('workingHours')
        if wh:
            working_hours_list.append(wh)

    candidates = slots_in_window(window_start, window_end, slot_minutes)
    out = []
    for slot in candidates:
        if any(overlaps(slot, b) for b in busy_dts):
            continue
        if not _slot_within_working_hours(slot, working_hours_list, window_zone):
            continue
        out.append((
            slot[0].strftime('%Y-%m-%dT%H:%M:%S'),
            slot[1].strftime('%Y-%m-%dT%H:%M:%S'),
        ))
    return out
