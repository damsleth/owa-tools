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
from datetime import time

from .dates import overlaps, parse_local_iso, slots_in_window

# Graph daysOfWeek strings -> Python weekday() index (Mon=0 .. Sun=6).
_WEEKDAY_INDEX = {
    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
    'friday': 4, 'saturday': 5, 'sunday': 6,
}


def _parse_working_hours(raw):
    """Project Graph workingHours into {days: set[int], start: time, end: time}
    or None when absent/unparseable. start/end are wall-clock times in the
    attendee's own working-hours time zone, which we treat as the same local
    wall clock the rest of the finder uses (getSchedule already renders every
    time in the requested zone)."""
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
    return {'days': days, 'start': start, 'end': end}


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
            'status': status,
            'subject': it.get('subject') or '',
        })
    return out


def _slot_within_working_hours(slot, working_hours_list):
    """A slot is allowed only if every attendee that advertises
    workingHours is working then: the slot's weekday is one of that
    attendee's working days and the slot fits inside [start, end).
    Attendees without parseable workingHours impose no constraint."""
    slot_start, slot_end = slot
    weekday = slot_start.weekday()
    slot_start_t = slot_start.time()
    slot_end_t = slot_end.time()
    for wh in working_hours_list:
        if weekday not in wh['days']:
            return False
        if slot_start_t < wh['start'] or slot_end_t > wh['end']:
            return False
    return True


def find_open_slots(attendees, window_start, window_end, slot_minutes):
    """Return slot tuples (start_iso, end_iso) within
    [window_start, window_end) where every attendee is free and
    (when advertised) inside every attendee's own workingHours.

    `attendees` is a list of normalized dicts (output of
    normalize_attendee). `window_start` / `window_end` are ISO local
    strings. Slot times are returned as ISO local strings to match.
    """
    busy_dts = []
    working_hours_list = []
    for a in attendees:
        for b in a.get('busy') or []:
            try:
                busy_dts.append(
                    (parse_local_iso(b['start']), parse_local_iso(b['end']))
                )
            except (ValueError, KeyError):
                continue
        wh = a.get('workingHours')
        if wh:
            working_hours_list.append(wh)

    candidates = slots_in_window(window_start, window_end, slot_minutes)
    out = []
    for slot in candidates:
        if any(overlaps(slot, b) for b in busy_dts):
            continue
        if not _slot_within_working_hours(slot, working_hours_list):
            continue
        out.append((
            slot[0].strftime('%Y-%m-%dT%H:%M:%S'),
            slot[1].strftime('%Y-%m-%dT%H:%M:%S'),
        ))
    return out
