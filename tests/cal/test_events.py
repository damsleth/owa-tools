"""Tests for event JSON shaping.

The `build_patch_json` tests anchor a load-bearing invariant: only
provided fields land in the output. Regressing that silently clobbers
untouched event fields.
"""
from owa_cal.events import (
    build_event_json,
    build_patch_json,
    is_dst_europe,
    normalize_event,
    normalize_events,
    to_local,
)
from datetime import datetime


def test_normalize_event_pascal():
    e = {
        'Id': 'AAMk',
        'Subject': 'Standup',
        'Start': {'DateTime': '2026-04-20T09:00:00', 'TimeZone': 'UTC'},
        'End': {'DateTime': '2026-04-20T09:30:00', 'TimeZone': 'UTC'},
        'Location': {'DisplayName': 'Room 1'},
        'Categories': ['ProjectX'],
        'ShowAs': 'Busy',
        'IsAllDay': False,
    }
    out = normalize_event(e)
    assert out['id'] == 'AAMk'
    assert out['subject'] == 'Standup'
    assert out['location'] == 'Room 1'
    assert out['categories'] == ['ProjectX']
    assert out['showAs'] == 'Busy'
    assert out['isAllDay'] is False


def test_normalize_events_empty():
    assert normalize_events({'value': []}) == []


def test_is_dst_europe_winter():
    assert is_dst_europe(datetime(2026, 1, 15)) is False
    assert is_dst_europe(datetime(2026, 12, 15)) is False


def test_is_dst_europe_summer():
    assert is_dst_europe(datetime(2026, 6, 15)) is True


def test_is_dst_europe_transition_hours():
    assert is_dst_europe(datetime(2026, 3, 29, 1, 59), 1) is False
    assert is_dst_europe(datetime(2026, 3, 29, 2, 0), 1) is True
    assert is_dst_europe(datetime(2026, 10, 25, 2, 59), 1) is True
    assert is_dst_europe(datetime(2026, 10, 25, 3, 0), 1) is False


def test_to_local_empty_returns_empty():
    assert to_local('') == ''


def test_to_local_known_tz_roundtrip_is_string():
    # Regardless of host tz we should get an ISO string back without crashing.
    out = to_local('2026-07-01T12:00:00', 'W. Europe Standard Time')
    assert 'T' in out and len(out) == 19


def test_to_local_utc_to_oslo_winter(force_tz):
    """Anchor for the DST bug: a winter UTC timestamp in Europe/Oslo
    should be +01:00, not +02:00."""
    force_tz('Europe/Oslo')
    assert to_local('2026-01-15T09:00:00', 'UTC') == '2026-01-15T10:00:00'


def test_to_local_utc_to_oslo_summer(force_tz):
    """Summer UTC -> Oslo should be +02:00 (DST)."""
    force_tz('Europe/Oslo')
    assert to_local('2026-07-15T09:00:00', 'UTC') == '2026-07-15T11:00:00'


def test_to_local_unspecified_tz_assumes_utc(force_tz):
    force_tz('Europe/Oslo')
    # No tz_name provided -> treated as UTC
    assert to_local('2026-01-15T09:00:00') == '2026-01-15T10:00:00'


def test_to_local_aware_datetime_respects_offset(force_tz):
    force_tz('Europe/Oslo')
    # Input already carries +00:00; should still reach Oslo winter time
    assert to_local('2026-01-15T09:00:00+00:00') == '2026-01-15T10:00:00'


def test_to_local_fractional_aware_datetime_preserves_offset(force_tz):
    force_tz('UTC')
    assert to_local('2026-01-15T09:00:00.1234567+02:00') == '2026-01-15T07:00:00'


def test_to_local_windows_zone_dst_start_boundary(force_tz):
    force_tz('Europe/Oslo')
    assert to_local('2026-03-29T01:30:00', 'W. Europe Standard Time') == '2026-03-29T01:30:00'


def test_to_local_us_zone_uses_dst(force_tz):
    force_tz('UTC')
    assert to_local('2026-07-15T12:00:00', 'Eastern Standard Time') == '2026-07-15T16:00:00'


# --- build_event_json ---

def test_build_event_minimal():
    body = build_event_json(
        'Lunsj', '2026-04-20T11:00:00', '2026-04-20T11:30:00',
        'W. Europe Standard Time',
    )
    assert body['Subject'] == 'Lunsj'
    assert body['Start']['DateTime'] == '2026-04-20T11:00:00'
    assert body['ShowAs'] == 'Busy'
    assert 'Categories' not in body
    assert 'Location' not in body
    assert 'Body' not in body


def test_build_event_with_optional_fields():
    body = build_event_json(
        'X', '2026-04-20T09:00:00', '2026-04-20T10:00:00', 'UTC',
        category='ProjectX', location='Room 1', body_text='notes',
        allday=True, showas='Free',
    )
    assert body['Subject'] == 'X'
    assert body['Categories'] == ['ProjectX']
    assert body['Location'] == {'DisplayName': 'Room 1'}
    assert body['Body'] == {'ContentType': 'Text', 'Content': 'notes'}
    assert body['ShowAs'] == 'Free'
    assert body['IsAllDay'] is True


# --- build_patch_json: only provided fields ---

def test_patch_only_provided_fields():
    patch = build_patch_json({'subject': 'New'}, 'W. Europe Standard Time')
    assert patch == {'Subject': 'New'}


def test_patch_empty_input_empty_output():
    assert build_patch_json({}, 'UTC') == {}


def test_patch_category_wraps_in_list():
    patch = build_patch_json({'category': 'ProjectX'}, 'UTC')
    assert patch == {'Categories': ['ProjectX']}


def test_patch_start_end_include_timezone():
    patch = build_patch_json(
        {'start': '2026-04-20T09:00:00', 'end': '2026-04-20T10:00:00'},
        'W. Europe Standard Time',
    )
    assert patch == {
        'Start': {'DateTime': '2026-04-20T09:00:00', 'TimeZone': 'W. Europe Standard Time'},
        'End': {'DateTime': '2026-04-20T10:00:00', 'TimeZone': 'W. Europe Standard Time'},
    }


def test_patch_body_content_type():
    patch = build_patch_json({'body': 'notes'}, 'UTC')
    assert patch == {'Body': {'ContentType': 'Text', 'Content': 'notes'}}


def test_patch_multiple_fields():
    patch = build_patch_json(
        {'subject': 'S', 'location': 'L', 'showas': 'Free'},
        'UTC',
    )
    assert patch == {
        'Subject': 'S',
        'Location': {'DisplayName': 'L'},
        'ShowAs': 'Free',
    }
