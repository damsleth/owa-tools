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
from .dates import overlaps, parse_local_iso, slots_in_window


def normalize_attendee(entry):
    """Project a Graph schedule entry into a flat shape."""
    out = {
        'email': entry.get('scheduleId') or '',
        'availabilityView': entry.get('availabilityView') or '',
        'busy': [],
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


def find_open_slots(attendees, window_start, window_end, slot_minutes):
    """Return slot tuples (start_iso, end_iso) within
    [window_start, window_end) where every attendee is free.

    `attendees` is a list of normalized dicts (output of
    normalize_attendee). `window_start` / `window_end` are ISO local
    strings. Slot times are returned as ISO local strings to match.
    """
    busy_dts = []
    for a in attendees:
        for b in a.get('busy') or []:
            try:
                busy_dts.append(
                    (parse_local_iso(b['start']), parse_local_iso(b['end']))
                )
            except (ValueError, KeyError):
                continue

    candidates = slots_in_window(window_start, window_end, slot_minutes)
    out = []
    for slot in candidates:
        if any(overlaps(slot, b) for b in busy_dts):
            continue
        out.append((
            slot[0].strftime('%Y-%m-%dT%H:%M:%S'),
            slot[1].strftime('%Y-%m-%dT%H:%M:%S'),
        ))
    return out
