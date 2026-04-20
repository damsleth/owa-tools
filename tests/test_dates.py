"""Tests for date helpers."""
from cal_cli.dates import iso_week_range, make_datetime, resolve_date, today


def test_resolve_date_passthrough():
    assert resolve_date('2026-04-20') == '2026-04-20'


def test_resolve_date_keywords_are_iso():
    for kw in ('today', 'tomorrow', 'yesterday'):
        out = resolve_date(kw)
        # YYYY-MM-DD shape
        assert len(out) == 10
        assert out[4] == '-' and out[7] == '-'


def test_today_is_iso():
    assert len(today()) == 10


def test_iso_week_range_w16_2026():
    mon, sun = iso_week_range(16, 2026)
    # ISO week 16 of 2026: 2026-04-13 (Mon) through 2026-04-19 (Sun)
    assert mon == '2026-04-13'
    assert sun == '2026-04-19'


def test_iso_week_range_accepts_strings():
    mon, sun = iso_week_range('16', '2026')
    assert mon == '2026-04-13' and sun == '2026-04-19'


def test_make_datetime_with_hhmm():
    assert make_datetime('2026-04-20', '09:30') == '2026-04-20T09:30:00'


def test_make_datetime_with_hhmmss():
    assert make_datetime('2026-04-20', '09:30:45') == '2026-04-20T09:30:45'


def test_make_datetime_empty_time_midnight():
    assert make_datetime('2026-04-20', '') == '2026-04-20T00:00:00'


def test_make_datetime_passthrough_if_already_full():
    assert make_datetime('2026-04-20T09:00:00', '') == '2026-04-20T09:00:00'
