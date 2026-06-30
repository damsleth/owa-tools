"""Pure-function tests for schedule.py: normalisation + slot finding."""
from datetime import time

from owa_sched.schedule import (
    _parse_time_of_day,
    _parse_working_hours,
    find_open_slots,
    normalize_attendee,
)


def test_normalize_attendee_keeps_busy_drops_free():
    upstream = {
        'scheduleId': 'alice@x.com',
        'availabilityView': '0220',
        'scheduleItems': [
            {'status': 'busy',
             'start': {'dateTime': '2026-05-04T09:00:00'},
             'end': {'dateTime': '2026-05-04T10:00:00'},
             'subject': 'Standup'},
            {'status': 'free',
             'start': {'dateTime': '2026-05-04T10:00:00'},
             'end': {'dateTime': '2026-05-04T11:00:00'}},
            {'status': 'tentative',
             'start': {'dateTime': '2026-05-04T11:00:00'},
             'end': {'dateTime': '2026-05-04T11:30:00'},
             'subject': 'Maybe'},
        ],
    }
    out = normalize_attendee(upstream)
    assert out['email'] == 'alice@x.com'
    assert len(out['busy']) == 2
    statuses = [b['status'] for b in out['busy']]
    assert 'busy' in statuses and 'tentative' in statuses
    assert 'free' not in statuses


def test_normalize_attendee_captures_error():
    upstream = {
        'scheduleId': 'gone@x.com',
        'error': {'message': 'mailbox not found'},
    }
    out = normalize_attendee(upstream)
    assert out['error'] == 'mailbox not found'
    assert out['busy'] == []


def test_find_open_slots_avoids_busy():
    attendees = [
        {
            'email': 'alice@x.com',
            'busy': [
                {'start': '2026-05-04T09:00:00',
                 'end': '2026-05-04T10:00:00', 'status': 'busy'},
            ],
            'error': None,
        },
        {
            'email': 'bob@x.com',
            'busy': [
                {'start': '2026-05-04T11:00:00',
                 'end': '2026-05-04T12:00:00', 'status': 'busy'},
            ],
            'error': None,
        },
    ]
    slots = find_open_slots(
        attendees,
        '2026-05-04T08:00:00', '2026-05-04T13:00:00',
        30,
    )
    # Both 09:00-10:00 (alice busy) and 11:00-12:00 (bob busy) excluded.
    # Window 08:00-13:00 with 30-min slots = 10 candidates total;
    # 4 are blocked (two 30-min slots inside each busy block).
    assert len(slots) == 6
    flat = [s[0] for s in slots]
    assert '2026-05-04T09:00:00' not in flat
    assert '2026-05-04T09:30:00' not in flat
    assert '2026-05-04T11:00:00' not in flat
    assert '2026-05-04T11:30:00' not in flat
    assert '2026-05-04T08:00:00' in flat
    assert '2026-05-04T10:00:00' in flat
    assert '2026-05-04T12:30:00' in flat


def test_find_open_slots_empty_when_fully_busy():
    attendees = [{
        'email': 'a@x.com',
        'busy': [{
            'start': '2026-05-04T09:00:00',
            'end': '2026-05-04T17:00:00',
            'status': 'busy',
        }],
        'error': None,
    }]
    slots = find_open_slots(
        attendees, '2026-05-04T09:00:00', '2026-05-04T17:00:00', 30,
    )
    assert slots == []


def test_find_open_slots_no_attendees_means_all_open():
    slots = find_open_slots(
        [], '2026-05-04T09:00:00', '2026-05-04T10:00:00', 30,
    )
    assert len(slots) == 2


# ---------------------------------------------------------------------------
# workingHours parsing
# ---------------------------------------------------------------------------

def test_parse_time_of_day_trims_fractional_seconds():
    assert _parse_time_of_day('08:30:00.0000000') == time(8, 30)
    assert _parse_time_of_day('17:00:00') == time(17, 0)


def test_parse_time_of_day_rejects_garbage():
    assert _parse_time_of_day('') is None
    assert _parse_time_of_day(None) is None
    assert _parse_time_of_day('nope') is None
    assert _parse_time_of_day('99:99:00') is None


def test_parse_working_hours_happy_path():
    wh = _parse_working_hours({
        'daysOfWeek': ['monday', 'Tuesday', 'WEDNESDAY'],
        'startTime': '08:00:00.0000000',
        'endTime': '16:00:00.0000000',
        'timeZone': {'name': 'W. Europe Standard Time'},
    })
    assert wh['days'] == {0, 1, 2}
    assert wh['start'] == time(8, 0)
    assert wh['end'] == time(16, 0)


def test_parse_working_hours_returns_none_when_incomplete():
    assert _parse_working_hours(None) is None
    assert _parse_working_hours('nope') is None
    assert _parse_working_hours({'daysOfWeek': [], 'startTime': '08:00:00',
                                 'endTime': '17:00:00'}) is None
    assert _parse_working_hours({'daysOfWeek': ['monday'],
                                 'startTime': 'bad', 'endTime': '17:00:00'}) is None


def test_normalize_attendee_captures_working_hours():
    out = normalize_attendee({
        'scheduleId': 'a@x.com',
        'scheduleItems': [],
        'workingHours': {
            'daysOfWeek': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
            'startTime': '09:00:00.0000000',
            'endTime': '17:00:00.0000000',
        },
    })
    assert out['workingHours']['days'] == {0, 1, 2, 3, 4}
    assert out['workingHours']['start'] == time(9, 0)


def test_normalize_attendee_working_hours_none_when_absent():
    out = normalize_attendee({'scheduleId': 'a@x.com', 'scheduleItems': []})
    assert out['workingHours'] is None


# ---------------------------------------------------------------------------
# working-hours-aware slot finding
# ---------------------------------------------------------------------------

def _attendee_with_wh(email, *, days, start, end, busy=None):
    return {
        'email': email,
        'busy': busy or [],
        'workingHours': {'days': set(days), 'start': start, 'end': end},
        'error': None,
    }


def test_find_open_slots_respects_working_window():
    # 2026-05-04 is a Monday. Attendee works Mon-Fri 10:00-12:00 only.
    attendees = [_attendee_with_wh(
        'a@x.com', days=range(5), start=time(10, 0), end=time(12, 0),
    )]
    slots = find_open_slots(
        attendees, '2026-05-04T08:00:00', '2026-05-04T17:00:00', 60,
    )
    starts = [s[0] for s in slots]
    assert starts == ['2026-05-04T10:00:00', '2026-05-04T11:00:00']


def test_find_open_slots_excludes_non_working_day():
    # 2026-05-09 is a Saturday; attendee works Mon-Fri only -> no slots.
    attendees = [_attendee_with_wh(
        'a@x.com', days=range(5), start=time(8, 0), end=time(17, 0),
    )]
    slots = find_open_slots(
        attendees, '2026-05-09T08:00:00', '2026-05-09T17:00:00', 60,
    )
    assert slots == []


def test_find_open_slots_intersects_two_attendees_windows():
    # Monday. a works 08-12, b works 11-17 -> overlap is 11-12 only.
    attendees = [
        _attendee_with_wh('a@x.com', days=range(5), start=time(8, 0), end=time(12, 0)),
        _attendee_with_wh('b@x.com', days=range(5), start=time(11, 0), end=time(17, 0)),
    ]
    slots = find_open_slots(
        attendees, '2026-05-04T08:00:00', '2026-05-04T17:00:00', 60,
    )
    assert [s[0] for s in slots] == ['2026-05-04T11:00:00']


def test_find_open_slots_attendee_without_wh_adds_no_constraint():
    # One attendee has no workingHours; only the other's window applies.
    attendees = [
        _attendee_with_wh('a@x.com', days=range(5), start=time(10, 0), end=time(11, 0)),
        {'email': 'b@x.com', 'busy': [], 'workingHours': None, 'error': None},
    ]
    slots = find_open_slots(
        attendees, '2026-05-04T08:00:00', '2026-05-04T17:00:00', 60,
    )
    assert [s[0] for s in slots] == ['2026-05-04T10:00:00']
