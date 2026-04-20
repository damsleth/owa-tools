"""Tests for the --pretty formatter."""
from cal_cli.format import format_events_pretty


def test_empty_message():
    assert format_events_pretty([]) == 'No events found.'


def test_groups_by_date_and_sorts_by_start():
    events = [
        {'subject': 'B', 'start': '2026-04-20T10:00:00', 'end': '2026-04-20T11:00:00',
         'location': '', 'categories': []},
        {'subject': 'A', 'start': '2026-04-20T09:00:00', 'end': '2026-04-20T09:30:00',
         'location': 'Room', 'categories': ['Cat']},
        {'subject': 'C', 'start': '2026-04-21T08:00:00', 'end': '2026-04-21T08:30:00',
         'location': '', 'categories': []},
    ]
    out = format_events_pretty(events)
    lines = out.splitlines()
    # Date headers present
    assert '2026-04-20' in lines
    assert '2026-04-21' in lines
    # A comes before B under 2026-04-20
    i_a = next(i for i, l in enumerate(lines) if 'A' in l and '09:00' in l)
    i_b = next(i for i, l in enumerate(lines) if 'B' in l and '10:00' in l)
    assert i_a < i_b


def test_renders_categories_and_location():
    events = [
        {'subject': 'X', 'start': '2026-04-20T09:00:00', 'end': '2026-04-20T10:00:00',
         'location': 'Room 42', 'categories': ['Alpha', 'Beta']},
    ]
    out = format_events_pretty(events)
    assert 'Room 42' in out
    assert '[Alpha, Beta]' in out
