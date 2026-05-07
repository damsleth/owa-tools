"""Pure-function tests for dates.py."""
from datetime import date, datetime

from owa_sched.dates import (
    daterange,
    iso_week_range,
    make_local_iso,
    overlaps,
    parse_hhmm,
    parse_local_iso,
    resolve_date,
    slots_in_window,
)


def test_resolve_date_keywords():
    assert resolve_date('today') == date.today().isoformat()
    assert resolve_date('') == date.today().isoformat()


def test_resolve_date_explicit():
    assert resolve_date('2026-05-12') == '2026-05-12'


def test_parse_hhmm_strict():
    t = parse_hhmm('09:30')
    assert t.hour == 9 and t.minute == 30


def test_iso_week_range_returns_mon_fri():
    mon, fri = iso_week_range(19, 2026)
    assert mon == '2026-05-04'
    assert fri == '2026-05-08'


def test_make_local_iso_round_trip():
    s = make_local_iso('2026-05-04', '09:30')
    assert s == '2026-05-04T09:30:00'
    dt = parse_local_iso(s)
    assert dt == datetime(2026, 5, 4, 9, 30)


def test_parse_local_iso_strips_fractional():
    dt = parse_local_iso('2026-05-04T09:30:00.0000000')
    assert dt == datetime(2026, 5, 4, 9, 30)


def test_daterange_inclusive():
    out = daterange('2026-05-04', '2026-05-06')
    assert out == ['2026-05-04', '2026-05-05', '2026-05-06']


def test_daterange_single_day():
    out = daterange('2026-05-04', '2026-05-04')
    assert out == ['2026-05-04']


def test_slots_in_window_30min():
    out = slots_in_window(
        '2026-05-04T09:00:00', '2026-05-04T10:30:00', 30,
    )
    assert len(out) == 3
    assert out[0][0] == datetime(2026, 5, 4, 9, 0)
    assert out[-1][1] == datetime(2026, 5, 4, 10, 30)


def test_slots_in_window_does_not_overflow():
    out = slots_in_window(
        '2026-05-04T09:00:00', '2026-05-04T09:45:00', 30,
    )
    # 45-min window with 30-min slots -> only one slot fits (09:00-09:30)
    assert len(out) == 1


def test_overlaps_half_open():
    a = (datetime(2026, 5, 4, 9, 0), datetime(2026, 5, 4, 10, 0))
    b = (datetime(2026, 5, 4, 9, 30), datetime(2026, 5, 4, 10, 30))
    c = (datetime(2026, 5, 4, 10, 0), datetime(2026, 5, 4, 11, 0))
    assert overlaps(a, b) is True
    # Touching at the boundary is NOT overlap (half-open).
    assert overlaps(a, c) is False
