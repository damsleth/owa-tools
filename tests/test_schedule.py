"""Pure-function tests for schedule.py: normalisation + slot finding."""
from owa_sched.schedule import find_open_slots, normalize_attendee


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
