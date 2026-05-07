"""Tests for the iCalendar (webcal) reader.

No network: `fetch_ics` is exercised via monkeypatch on `urlopen`.
"""
from pathlib import Path

from owa_cal import ics as ics_mod


FIXTURE = Path(__file__).parent / 'fixtures' / 'sample.ics'


def _load():
    return FIXTURE.read_text()


def test_parse_yields_expected_event_count():
    events = ics_mod.parse_ics(_load())
    # Four VEVENTs in the fixture; nested VALARMs must not bleed in.
    assert len(events) == 4


def test_valarm_block_does_not_leak_into_parent_event():
    events = ics_mod.parse_ics(_load())
    first = events[0]
    # The VALARM block has its own DESCRIPTION ("Internal council: February").
    # The parent VEVENT's DESCRIPTION must win.
    assert 'Agenda item 1' in first['description']
    assert 'Internal council: February' not in first['description']


def test_text_escapes_decoded():
    events = ics_mod.parse_ics(_load())
    body = events[0]['description']
    # \n -> newline, \, -> comma
    assert 'Agenda item 1\nAgenda item 2, with comma\nLine three' == body


def test_attendee_garble_does_not_crash_parser():
    """The fixture has two ATTENDEE lines concatenated with no separator,
    matching a real producer bug. The parser must skip / ignore them
    cleanly without affecting the rest of the event."""
    events = ics_mod.parse_ics(_load())
    assert events[0]['summary'] == 'Internal council meeting (February)'


def test_utc_datetime_is_converted_to_local(force_tz):
    force_tz('Europe/Oslo')
    events = ics_mod.parse_ics(_load())
    norm = ics_mod.ics_event_to_normalized(events[0])
    # 16:30 UTC on 2026-02-10 in Oslo (winter, UTC+1) -> 17:30 local.
    assert norm['start'] == '2026-02-10T17:30:00'
    assert norm['end'] == '2026-02-10T21:00:00'
    assert norm['isAllDay'] is False


def test_all_day_event_uses_value_date_form():
    events = ics_mod.parse_ics(_load())
    holiday = events[2]
    norm = ics_mod.ics_event_to_normalized(holiday)
    assert norm['isAllDay'] is True
    assert norm['start'] == '2026-05-01'
    assert norm['end'] == '2026-05-02'


def test_line_folding_is_unfolded():
    events = ics_mod.parse_ics(_load())
    folded = events[3]
    # The continuation line begins with one space; it must merge into
    # SUMMARY without that leading space.
    assert folded['summary'] == 'Folded summary(continuation line) trailing text'


def test_normalized_shape_matches_outlook_path():
    events = ics_mod.parse_ics(_load())
    norm = ics_mod.ics_event_to_normalized(events[0])
    # Match the keys produced by events.normalize_event so the pretty
    # formatter handles both sources without branching, plus the new
    # optional `body` field this path populates.
    expected_keys = {
        'id', 'subject', 'start', 'end', 'categories',
        'location', 'showAs', 'isAllDay', 'body',
    }
    assert set(norm.keys()) == expected_keys
    assert norm['id'] == '00000000-0000-0000-0000-000000000001'
    assert norm['location'] == 'Sample Room A'
    assert norm['categories'] == []
    assert norm['showAs'] == ''


def test_filter_by_range_inclusive():
    events = [
        {'start': '2026-02-10T17:30:00'},
        {'start': '2026-03-11T18:00:00'},
        {'start': '2026-05-01'},
    ]
    out = ics_mod.filter_by_range(events, '2026-03-01', '2026-04-30')
    assert len(out) == 1
    assert out[0]['start'].startswith('2026-03-11')


def test_filter_by_range_open_ended():
    events = [
        {'start': '2026-02-10T17:30:00'},
        {'start': '2026-03-11T18:00:00'},
    ]
    out = ics_mod.filter_by_range(events, '', '2026-02-28')
    assert len(out) == 1
    assert out[0]['start'].startswith('2026-02-10')


def test_filter_by_subject_case_insensitive():
    events = [
        {'subject': 'Internal council meeting (February)'},
        {'subject': 'Election night'},
    ]
    assert len(ics_mod.filter_by_subject(events, 'COUNCIL')) == 1
    assert len(ics_mod.filter_by_subject(events, '')) == 2


def test_webcal_scheme_is_rewritten_to_https(monkeypatch):
    """webcal:// is an advisory scheme; servers speak HTTPS. fetch_ics
    must rewrite before calling urlopen."""
    seen = {}

    class FakeResp:
        def read(self):
            return b'BEGIN:VCALENDAR\nEND:VCALENDAR\n'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        seen['url'] = req.full_url
        seen['ua'] = req.get_header('User-agent')
        return FakeResp()

    monkeypatch.setattr(ics_mod.request, 'urlopen', fake_urlopen)
    ics_mod.fetch_ics('webcal://example.invalid/feed?key=secret')
    assert seen['url'] == 'https://example.invalid/feed?key=secret'
    assert seen['ua'] and seen['ua'].startswith('owa-cal/')


def test_fetch_ics_decodes_utf8(monkeypatch):
    class FakeResp:
        def read(self):
            return 'SUMMARY:Lødrup\n'.encode('utf-8')

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(ics_mod.request, 'urlopen', lambda req, timeout=None: FakeResp())
    text = ics_mod.fetch_ics('https://example.invalid/feed')
    assert 'Lødrup' in text


def test_fetch_and_normalize_end_to_end(monkeypatch, force_tz):
    force_tz('UTC')

    class FakeResp:
        def read(self):
            return _load().encode('utf-8')

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(ics_mod.request, 'urlopen', lambda req, timeout=None: FakeResp())
    events = ics_mod.fetch_and_normalize('https://example.invalid/feed')
    assert len(events) == 4
    assert events[0]['start'] == '2026-02-10T16:30:00'
    assert events[0]['body'].startswith('Agenda item 1')
