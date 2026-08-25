"""Tests for event JSON shaping.

The `build_patch_json` tests anchor a load-bearing invariant: only
provided fields land in the output. Regressing that silently clobbers
untouched event fields.
"""
from datetime import datetime

import pytest

from owa_cal.events import (
    build_attendees,
    build_event_json,
    build_patch_json,
    build_recurrence,
    is_dst_europe,
    normalize_event,
    normalize_event_detail,
    normalize_events,
    to_local,
)


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
    # Absent Type/SeriesMasterId must read as a standalone event, never as an
    # unknown: a consumer that writes back has to be able to trust this.
    assert out['type'] == 'SingleInstance'
    assert out['seriesMasterId'] is None


def test_normalize_event_series_occurrence():
    """One occurrence of a recurring series is distinguishable from a
    standalone event. Callers that edit events need this: changing one
    Occurrence is a different operation from changing a SingleInstance, and
    guessing is not safe."""
    e = {
        'Id': 'OCC1',
        'Subject': 'Birthday',
        'Start': {'DateTime': '2026-08-28T00:00:00', 'TimeZone': 'UTC'},
        'End': {'DateTime': '2026-08-29T00:00:00', 'TimeZone': 'UTC'},
        'IsAllDay': True,
        'Type': 'Occurrence',
        'SeriesMasterId': 'MASTER1',
    }
    out = normalize_event(e)
    assert out['type'] == 'Occurrence'
    assert out['seriesMasterId'] == 'MASTER1'


def test_normalize_event_series_master():
    out = normalize_event({
        'Id': 'MASTER1',
        'Subject': 'Weekly sync',
        'Start': {'DateTime': '2026-08-24T09:00:00', 'TimeZone': 'UTC'},
        'End': {'DateTime': '2026-08-24T09:30:00', 'TimeZone': 'UTC'},
        'Type': 'SeriesMaster',
    })
    assert out['type'] == 'SeriesMaster'
    assert out['seriesMasterId'] is None


def test_normalize_events_empty():
    assert normalize_events({'value': []}) == []


def test_normalize_event_detail_extracts_rich_fields():
    e = {
        'Id': 'AAA', 'Subject': 'Hagefest',
        'Start': {'DateTime': '2026-06-05T17:00:00', 'TimeZone': 'UTC'},
        'End': {'DateTime': '2026-06-05T23:30:00', 'TimeZone': 'UTC'},
        'Organizer': {'EmailAddress': {'Name': 'Boss', 'Address': 'boss@x.com'}},
        'IsOrganizer': False,
        'ResponseStatus': {'Response': 'tentativelyAccepted'},
        'BodyPreview': '  HUSK PÅMELDINGSSKJEMA!  ',
        'Attendees': [
            {'EmailAddress': {'Name': 'Ada', 'Address': 'ada@x.com'},
             'Type': 'required', 'Status': {'Response': 'accepted'}},
            {'EmailAddress': {'Name': 'Bo', 'Address': 'bo@x.com'},
             'Type': 'optional', 'Status': {'Response': 'declined'}},
        ],
    }
    out = normalize_event_detail(e)
    # base fields still present
    assert out['subject'] == 'Hagefest'
    # rich fields the plain normalize_event drops
    assert out['organizer'] == 'Boss'
    assert out['response'] == 'tentativelyAccepted'
    assert out['isOrganizer'] is False
    assert out['body'] == 'HUSK PÅMELDINGSSKJEMA!'   # stripped
    assert out['attendees'] == [
        {'name': 'Ada', 'address': 'ada@x.com', 'type': 'required', 'response': 'accepted'},
        {'name': 'Bo', 'address': 'bo@x.com', 'type': 'optional', 'response': 'declined'},
    ]


def test_normalize_event_detail_tolerates_lean_event():
    # A lean event (no rich fields selected) degrades to empties, never raises.
    out = normalize_event_detail({'Id': 'X', 'Subject': 'S'})
    assert out['organizer'] == ''
    assert out['attendees'] == []
    assert out['body'] == ''
    assert out['response'] == ''


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


def test_patch_categories_list():
    patch = build_patch_json({'categories': ['ProjectX', 'Blue']}, 'UTC')
    assert patch == {'Categories': ['ProjectX', 'Blue']}


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


def test_patch_attendees_reminder_recurrence():
    patch = build_patch_json(
        {
            'attendees': [{'EmailAddress': {'Address': 'a@x.com'}, 'Type': 'Required'}],
            'reminder': 15,
            'recurrence': {'Pattern': {'Type': 'Daily', 'Interval': 1}},
        },
        'UTC',
    )
    assert patch['Attendees'] == [
        {'EmailAddress': {'Address': 'a@x.com'}, 'Type': 'Required'}
    ]
    assert patch['ReminderMinutesBeforeStart'] == 15
    assert patch['IsReminderOn'] is True
    assert patch['Recurrence'] == {'Pattern': {'Type': 'Daily', 'Interval': 1}}


# --- build_attendees ---

def test_build_attendees_required_and_optional():
    out = build_attendees(['a@x.com', '  '], ['b@x.com'])
    assert out == [
        {'EmailAddress': {'Address': 'a@x.com'}, 'Type': 'Required'},
        {'EmailAddress': {'Address': 'b@x.com'}, 'Type': 'Optional'},
    ]


def test_build_attendees_empty():
    assert build_attendees([], []) == []


# --- build_recurrence ---

def test_build_recurrence_none_when_no_recur():
    assert build_recurrence('', '2026-04-20') is None


def test_build_recurrence_daily_no_end():
    rec = build_recurrence('daily', '2026-04-20')
    assert rec['Pattern'] == {'Type': 'Daily', 'Interval': 1}
    assert rec['Range'] == {'Type': 'NoEnd', 'StartDate': '2026-04-20'}


def test_build_recurrence_weekly_anchors_on_weekday_with_count():
    # 2026-04-20 is a Monday
    rec = build_recurrence('weekly', '2026-04-20', interval=2, count=10)
    assert rec['Pattern']['Type'] == 'Weekly'
    assert rec['Pattern']['Interval'] == 2
    assert rec['Pattern']['DaysOfWeek'] == ['Monday']
    assert rec['Range'] == {
        'Type': 'Numbered', 'StartDate': '2026-04-20', 'NumberOfOccurrences': 10,
    }


def test_build_recurrence_until_end_date():
    rec = build_recurrence('daily', '2026-04-20', until='2026-05-20')
    assert rec['Range'] == {
        'Type': 'EndDate', 'StartDate': '2026-04-20', 'EndDate': '2026-05-20',
    }


def test_build_recurrence_unsupported_value_raises():
    with pytest.raises(ValueError):
        build_recurrence('hourly', '2026-04-20')


# --- build_event_json: new optional fields ---

def test_build_event_attendees_reminder_categories_recurrence():
    body = build_event_json(
        'Sync', '2026-04-20T09:00:00', '2026-04-20T09:30:00', 'UTC',
        categories=['A', 'B'],
        attendees=[{'EmailAddress': {'Address': 'a@x.com'}, 'Type': 'Required'}],
        reminder=15,
        recurrence={'Pattern': {'Type': 'Daily', 'Interval': 1}},
    )
    assert body['Categories'] == ['A', 'B']
    assert body['Attendees'] == [
        {'EmailAddress': {'Address': 'a@x.com'}, 'Type': 'Required'}
    ]
    assert body['ReminderMinutesBeforeStart'] == 15
    assert body['IsReminderOn'] is True
    assert body['Recurrence'] == {'Pattern': {'Type': 'Daily', 'Interval': 1}}


def test_build_event_no_reminder_keeps_reminder_off():
    body = build_event_json(
        'X', '2026-04-20T09:00:00', '2026-04-20T10:00:00', 'UTC',
    )
    assert body['IsReminderOn'] is False
    assert 'ReminderMinutesBeforeStart' not in body


def test_build_event_merges_legacy_category_with_categories():
    body = build_event_json(
        'X', '2026-04-20T09:00:00', '2026-04-20T10:00:00', 'UTC',
        category='Legacy', categories=['New', 'Legacy'],
    )
    # order preserved, dupes dropped
    assert body['Categories'] == ['Legacy', 'New']
