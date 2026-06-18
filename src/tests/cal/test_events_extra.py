"""Extra tests for owa_cal.events and owa_cal.ics to raise coverage above 90%.

Targets uncovered paths:
- events.py: _nth_weekday, _is_dst_us, _parse_outlook_datetime (fractional+suffix edge),
  _windows_zoneinfo (unmapped tz), _fallback_timezone (US DST + unknown tz),
  to_local (ValueError branch), _attendee_brief (non-dict input),
  normalize_events_detail, build_patch_json 'end' key
- ics.py: webcals:// rewrite, _split_params (param without =), _split_property (no colon),
  _zone_for_tzid (bad tzid), _parse_ical_datetime (invalid date, strptime failure,
  TZID-with-known-zone path), parse_ics (END without matching stack, nested VEVENT guard),
  filter_by_range (empty start dropped)
"""
from datetime import datetime

import pytest

from owa_cal import events as ev_mod
from owa_cal import ics as ics_mod


# ---------------------------------------------------------------------------
# events._nth_weekday (lines 73-82)
# ---------------------------------------------------------------------------

def test_nth_weekday_returns_correct_day():
    from owa_cal.events import _nth_weekday
    # Second Sunday (weekday 6) of March 2026 is the 8th
    day = _nth_weekday(2026, 3, 6, 2)
    assert day == 8


def test_nth_weekday_returns_zero_when_not_found():
    from owa_cal.events import _nth_weekday
    # There is no 6th Sunday in any month
    day = _nth_weekday(2026, 3, 6, 6)
    assert day == 0


# ---------------------------------------------------------------------------
# events._is_dst_us (lines 108-116)
# ---------------------------------------------------------------------------

def test_is_dst_us_winter_january():
    from owa_cal.events import _is_dst_us
    assert _is_dst_us(datetime(2026, 1, 15)) is False


def test_is_dst_us_december():
    from owa_cal.events import _is_dst_us
    assert _is_dst_us(datetime(2026, 12, 1)) is False


def test_is_dst_us_summer_july():
    from owa_cal.events import _is_dst_us
    assert _is_dst_us(datetime(2026, 7, 15)) is True


def test_is_dst_us_march_start_boundary():
    from owa_cal.events import _is_dst_us
    # 2026-03-08: second Sunday in March (DST starts 2:00)
    # Before 2:00 -> still standard time
    assert _is_dst_us(datetime(2026, 3, 8, 1, 59)) is False
    # At 2:00 -> DST
    assert _is_dst_us(datetime(2026, 3, 8, 2, 0)) is True


def test_is_dst_us_november_end_boundary():
    from owa_cal.events import _is_dst_us
    # First Sunday in November 2026 is the 1st
    # Before 2:00 -> still DST
    assert _is_dst_us(datetime(2026, 11, 1, 1, 59)) is True
    # At/after 2:00 -> standard time
    assert _is_dst_us(datetime(2026, 11, 1, 2, 0)) is False


def test_is_dst_us_march_day_before_start():
    from owa_cal.events import _is_dst_us
    # Day before DST start = not DST
    assert _is_dst_us(datetime(2026, 3, 7)) is False


def test_is_dst_us_november_day_after_end():
    from owa_cal.events import _is_dst_us
    # Day after DST end
    assert _is_dst_us(datetime(2026, 11, 2)) is False


# ---------------------------------------------------------------------------
# events._parse_outlook_datetime: fractional seconds without suffix (line 135)
# ---------------------------------------------------------------------------

def test_parse_outlook_datetime_fractional_no_offset():
    from owa_cal.events import _parse_outlook_datetime
    # Fractional seconds, no trailing tz offset: the frac branch with no suffix
    dt = _parse_outlook_datetime('2026-04-20T09:00:00.123456')
    assert dt.year == 2026
    assert dt.microsecond == 123456


def test_parse_outlook_datetime_z_suffix():
    from owa_cal.events import _parse_outlook_datetime
    dt = _parse_outlook_datetime('2026-04-20T09:00:00Z')
    assert dt.utcoffset().seconds == 0


# ---------------------------------------------------------------------------
# events._windows_zoneinfo: unmapped tz name (line 141, 143-144)
# ---------------------------------------------------------------------------

def test_windows_zoneinfo_unmapped_name_returns_none():
    from owa_cal.events import _windows_zoneinfo
    result = _windows_zoneinfo('Totally Unknown Timezone')
    assert result is None


# ---------------------------------------------------------------------------
# events._fallback_timezone: unknown tz returns UTC (line 153), US DST path
# ---------------------------------------------------------------------------

def test_fallback_timezone_unknown_returns_utc():
    from owa_cal.events import _fallback_timezone
    tz = _fallback_timezone('NonExistent Timezone', datetime(2026, 7, 1))
    from datetime import timezone
    assert tz == timezone.utc


def test_fallback_timezone_us_dst_active():
    from owa_cal.events import _fallback_timezone
    # Eastern in summer: base -5, DST +1 = -4
    tz = _fallback_timezone('Eastern Standard Time', datetime(2026, 7, 15, 12))
    from datetime import timedelta, timezone
    assert tz == timezone(timedelta(hours=-4))


def test_fallback_timezone_us_standard():
    from owa_cal.events import _fallback_timezone
    # Eastern in winter: base -5, no DST = -5
    tz = _fallback_timezone('Eastern Standard Time', datetime(2026, 1, 15, 12))
    from datetime import timedelta, timezone
    assert tz == timezone(timedelta(hours=-5))


# ---------------------------------------------------------------------------
# events.to_local: ValueError path (line 176-177)
# ---------------------------------------------------------------------------

def test_to_local_unparseable_returns_input():
    result = ev_mod.to_local('not-a-datetime')
    assert result == 'not-a-datetime'


# ---------------------------------------------------------------------------
# events._attendee_brief: non-dict input (line 219)
# ---------------------------------------------------------------------------

def test_attendee_brief_non_dict_input():
    from owa_cal.events import _attendee_brief
    result = _attendee_brief('plain-string-attendee')
    assert result['name'] == 'plain-string-attendee'
    assert result['address'] == ''
    assert result['type'] == ''
    assert result['response'] == ''


# ---------------------------------------------------------------------------
# events.normalize_events_detail (line 251)
# ---------------------------------------------------------------------------

def test_normalize_events_detail_collection():
    from owa_cal.events import normalize_events_detail
    response = {
        'value': [
            {
                'Id': 'A1',
                'Subject': 'Meeting',
                'Start': {'DateTime': '2026-04-20T10:00:00', 'TimeZone': 'UTC'},
                'End': {'DateTime': '2026-04-20T11:00:00', 'TimeZone': 'UTC'},
                'Organizer': {'EmailAddress': {'Name': 'Alice', 'Address': 'a@x.com'}},
                'IsOrganizer': True,
                'BodyPreview': 'details',
                'Attendees': [],
                'ResponseStatus': {'Response': 'accepted'},
            }
        ]
    }
    items = normalize_events_detail(response)
    assert len(items) == 1
    assert items[0]['organizer'] == 'Alice'
    assert items[0]['isOrganizer'] is True
    assert items[0]['body'] == 'details'


def test_normalize_events_detail_empty():
    from owa_cal.events import normalize_events_detail
    assert normalize_events_detail({'value': []}) == []


# ---------------------------------------------------------------------------
# events.build_patch_json: 'end' key (branch line 298->285 region)
# ---------------------------------------------------------------------------

def test_patch_end_key_builds_correctly():
    patch = ev_mod.build_patch_json({'end': '2026-04-20T11:00:00'}, 'UTC')
    assert patch == {
        'End': {'DateTime': '2026-04-20T11:00:00', 'TimeZone': 'UTC'},
    }


# ---------------------------------------------------------------------------
# ics._zone_for_tzid: bad tzid raises -> returns None (line 132-137)
# ---------------------------------------------------------------------------

def test_zone_for_tzid_invalid_returns_none():
    from owa_cal.ics import _zone_for_tzid
    result = _zone_for_tzid('NotARealTimezone/Invalid')
    assert result is None


def test_zone_for_tzid_empty_returns_none():
    from owa_cal.ics import _zone_for_tzid
    assert _zone_for_tzid('') is None


# ---------------------------------------------------------------------------
# ics._split_params: param without '=' is skipped (line 85)
# ---------------------------------------------------------------------------

def test_split_params_skips_param_without_equals():
    from owa_cal.ics import _split_params
    name, params = _split_params('DTSTART;BADPARAM;VALUE=DATE')
    assert name == 'DTSTART'
    assert 'BADPARAM' not in params
    assert params.get('VALUE') == 'DATE'


# ---------------------------------------------------------------------------
# ics._split_property: line with no colon returns (None, None, None) (line 107)
# ---------------------------------------------------------------------------

def test_split_property_no_colon_returns_nones():
    from owa_cal.ics import _split_property
    n, p, v = _split_property('NOCOHERINHERE')
    assert n is None
    assert p is None
    assert v is None


def test_split_property_quoted_colon_is_not_separator():
    from owa_cal.ics import _split_property
    # A colon inside quotes should not be treated as separator
    line = 'PROP;PARAM="a:b":value'
    n, p, v = _split_property(line)
    assert n == 'PROP'
    assert v == 'value'


# ---------------------------------------------------------------------------
# ics._parse_ical_datetime: various edge branches
# ---------------------------------------------------------------------------

def test_parse_ical_datetime_empty_value():
    from owa_cal.ics import _parse_ical_datetime
    s, all_day = _parse_ical_datetime('', {})
    assert s == ''
    assert all_day is False


def test_parse_ical_datetime_date_value_param():
    from owa_cal.ics import _parse_ical_datetime
    s, all_day = _parse_ical_datetime('20260420', {'VALUE': 'DATE'})
    assert s == '2026-04-20'
    assert all_day is True


def test_parse_ical_datetime_date_8digit():
    from owa_cal.ics import _parse_ical_datetime
    # 8-digit without VALUE=DATE param but looks like a date
    s, all_day = _parse_ical_datetime('20260420', {})
    assert s == '2026-04-20'
    assert all_day is True


def test_parse_ical_datetime_invalid_date_digits():
    from owa_cal.ics import _parse_ical_datetime
    # Passes the 8-digit isdigit check but invalid day -> ValueError branch
    s, all_day = _parse_ical_datetime('20261399', {'VALUE': 'DATE'})
    assert s == '20261399'
    assert all_day is True


def test_parse_ical_datetime_strptime_failure():
    from owa_cal.ics import _parse_ical_datetime
    # Not matching %Y%m%dT%H%M%S format -> ValueError -> returns raw
    s, all_day = _parse_ical_datetime('BAD-DATETIME', {})
    assert s == 'BAD-DATETIME'
    assert all_day is False


def test_parse_ical_datetime_utc_datetime():
    from owa_cal.ics import _parse_ical_datetime
    s, all_day = _parse_ical_datetime('20260420T090000Z', {})
    assert '2026-04-20' in s
    assert 'T' in s
    assert all_day is False


def test_parse_ical_datetime_floating_no_tzid():
    from owa_cal.ics import _parse_ical_datetime
    # No TZID, no Z -> floating time, returned as-is
    s, all_day = _parse_ical_datetime('20260420T090000', {})
    assert s == '2026-04-20T09:00:00'
    assert all_day is False


def test_parse_ical_datetime_with_tzid(force_tz):
    from owa_cal.ics import _parse_ical_datetime
    force_tz('UTC')
    # Valid TZID -> zone lookup succeeds -> local conversion
    s, all_day = _parse_ical_datetime('20260420T090000', {'TZID': 'Europe/Oslo'})
    # We just check it returns a non-empty string with T separator
    assert 'T' in s
    assert all_day is False


# ---------------------------------------------------------------------------
# ics.fetch_ics: webcals:// scheme rewrite (line 49)
# ---------------------------------------------------------------------------

def test_fetch_ics_webcals_scheme_rewritten(monkeypatch):
    """webcals:// should be rewritten to https:// before the request."""
    captured = {}

    class FakeResp:
        def read(self):
            return b'BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    def fake_urlopen(req, timeout):
        captured['url'] = req.full_url
        return FakeResp()

    monkeypatch.setattr(ics_mod.request, 'urlopen', fake_urlopen)
    ics_mod.fetch_ics('webcals://example.invalid/feed')
    assert captured['url'].startswith('https://')
    assert 'webcals' not in captured['url']


# ---------------------------------------------------------------------------
# ics.parse_ics: END without matching stack (line 211->216)
# ---------------------------------------------------------------------------

def test_parse_ics_end_without_stack_does_not_crash():
    text = 'END:VCALENDAR\r\n'
    events = ics_mod.parse_ics(text)
    assert events == []


def test_parse_ics_nested_vevent_guard():
    """A nested BEGIN:VEVENT while current is already set should not open a
    second event dict. The guard (`current is None`) must fire so the parser
    collects exactly one event rather than two from the same block.
    """
    text = (
        'BEGIN:VCALENDAR\r\n'
        'BEGIN:VEVENT\r\n'
        'SUMMARY:Outer\r\n'
        'UID:outer-1\r\n'
        'DTSTART:20260420T090000Z\r\n'
        'DTEND:20260420T100000Z\r\n'
        'BEGIN:VEVENT\r\n'
        'SUMMARY:Inner\r\n'
        'UID:inner-1\r\n'
        'END:VEVENT\r\n'
        'END:VEVENT\r\n'
        'END:VCALENDAR\r\n'
    )
    events = ics_mod.parse_ics(text)
    # The guard fires: only one event dict is collected total (not two)
    assert len(events) == 1


# ---------------------------------------------------------------------------
# ics.filter_by_range: event with empty start is dropped (line 282)
# ---------------------------------------------------------------------------

def test_filter_by_range_drops_event_with_no_start():
    events = [
        {'start': ''},
        {'start': None},
        {'subject': 'no start key'},
        {'start': '2026-04-20T09:00:00'},
    ]
    out = ics_mod.filter_by_range(events, '', '')
    assert len(out) == 1
    assert out[0]['start'] == '2026-04-20T09:00:00'


def test_filter_by_range_no_bounds_keeps_all_with_start():
    events = [
        {'start': '2026-01-01'},
        {'start': '2026-12-31'},
        {'start': ''},
    ]
    out = ics_mod.filter_by_range(events, '', '')
    assert len(out) == 2
