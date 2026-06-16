"""Tests for owa_core.periods relative/semantic resolution.

All "now" reads are pinned via today= so these are deterministic. Anchor dates
are chosen to exercise year/week rollover: 2026-06-15 is a Monday in ISO week
25, and 2026-01-01 / 2026-12-31 probe the boundaries.
"""
from datetime import date

import pytest

from owa_core import periods
from owa_core.errors import UsageError

MON_2026_W25 = date(2026, 6, 15)  # ISO 2026-W25-1


# --- resolve_week -----------------------------------------------------------

@pytest.mark.parametrize('value,expected', [
    ('current', (2026, 25)),
    ('this', (2026, 25)),
    ('last', (2026, 24)),
    ('prev', (2026, 24)),
    ('previous', (2026, 24)),
    ('next', (2026, 26)),
    ('+1', (2026, 26)),
    ('-1', (2026, 24)),
    ('+2', (2026, 27)),
    (16, (2026, 16)),
    ('16', (2026, 16)),
])
def test_resolve_week(value, expected):
    assert periods.resolve_week(value, today=MON_2026_W25) == expected


def test_resolve_week_year_rolls_back():
    # First ISO week of 2026; one week back lands in 2025 (52 weeks).
    anchor = date(2026, 1, 1)  # ISO 2026-W01
    assert periods.resolve_week('-1', today=anchor) == (2025, 52)


def test_resolve_week_year_rolls_forward():
    anchor = date(2025, 12, 31)  # ISO 2026-W01
    assert periods.resolve_week('+1', today=anchor) == (2026, 2)


def test_resolve_week_absolute_year_override():
    assert periods.resolve_week(16, today=MON_2026_W25, year=2024) == (2024, 16)


def test_resolve_week_rejects_out_of_range():
    with pytest.raises(UsageError):
        periods.resolve_week(54, today=MON_2026_W25)
    with pytest.raises(UsageError):
        periods.resolve_week(0, today=MON_2026_W25)


def test_resolve_week_rejects_garbage():
    with pytest.raises(UsageError):
        periods.resolve_week('soon', today=MON_2026_W25)


def test_resolve_week_rejects_malformed_offset():
    # Leading sign but not a valid integer.
    with pytest.raises(UsageError):
        periods.resolve_week('+x', today=MON_2026_W25)


def test_resolve_week_53_validation():
    # 2025 has only 52 ISO weeks, so week 53 is invalid there.
    with pytest.raises(UsageError):
        periods.resolve_week(53, today=date(2025, 6, 1))
    # 2026 starts on a Thursday, so it genuinely has week 53.
    assert periods.resolve_week(53, today=MON_2026_W25) == (2026, 53)


# --- resolve_month ----------------------------------------------------------

@pytest.mark.parametrize('value,expected', [
    ('current', (2026, 6)),
    ('this', (2026, 6)),
    ('last', (2026, 5)),
    ('next', (2026, 7)),
    ('+1', (2026, 7)),
    ('-1', (2026, 5)),
    ('-2', (2026, 4)),
    (3, (2026, 3)),
    ('12', (2026, 12)),
])
def test_resolve_month(value, expected):
    assert periods.resolve_month(value, today=MON_2026_W25) == expected


def test_resolve_month_rolls_forward():
    assert periods.resolve_month('+1', today=date(2026, 12, 10)) == (2027, 1)


def test_resolve_month_rolls_back():
    assert periods.resolve_month('-1', today=date(2026, 1, 10)) == (2025, 12)


def test_resolve_month_big_offset():
    assert periods.resolve_month('+13', today=date(2026, 6, 15)) == (2027, 7)


def test_resolve_month_absolute_year_override():
    assert periods.resolve_month(3, today=MON_2026_W25, year=2030) == (2030, 3)


def test_resolve_month_rejects_out_of_range():
    with pytest.raises(UsageError):
        periods.resolve_month(13, today=MON_2026_W25)
    with pytest.raises(UsageError):
        periods.resolve_month(0, today=MON_2026_W25)


# --- resolve_year -----------------------------------------------------------

@pytest.mark.parametrize('value,expected', [
    ('current', 2026),
    ('this', 2026),
    ('last', 2025),
    ('next', 2027),
    ('+1', 2027),
    ('-1', 2025),
    ('+5', 2031),
    (2030, 2030),
    ('2030', 2030),
    (100, 100),
])
def test_resolve_year(value, expected):
    assert periods.resolve_year(value, today=MON_2026_W25) == expected


def test_resolve_year_rejects_ambiguous_small_bare():
    with pytest.raises(UsageError):
        periods.resolve_year(2, today=MON_2026_W25)
    with pytest.raises(UsageError):
        periods.resolve_year(99, today=MON_2026_W25)


def test_resolve_year_rejects_garbage():
    with pytest.raises(UsageError):
        periods.resolve_year('soon', today=MON_2026_W25)


def test_resolve_year_rejects_malformed_offset():
    with pytest.raises(UsageError):
        periods.resolve_year('-x', today=MON_2026_W25)


# --- resolve_day ------------------------------------------------------------

@pytest.mark.parametrize('value,expected', [
    ('today', '2026-06-15'),
    ('', '2026-06-15'),
    ('tomorrow', '2026-06-16'),
    ('yesterday', '2026-06-14'),
    ('+1', '2026-06-16'),
    ('-3', '2026-06-12'),
    ('2024-02-29', '2024-02-29'),
])
def test_resolve_day_simple(value, expected):
    assert periods.resolve_day(value, today=MON_2026_W25) == expected


@pytest.mark.parametrize('value,expected', [
    ('monday', '2026-06-15'),
    ('mon', '2026-06-15'),
    ('wednesday', '2026-06-17'),
    ('sunday', '2026-06-21'),
    ('friday', '2026-06-19'),
])
def test_resolve_day_weekday_current_week(value, expected):
    # Mon-anchored: on Monday, earlier weekdays are still "this week".
    assert periods.resolve_day(value, today=MON_2026_W25) == expected


def test_resolve_day_weekday_can_be_in_past():
    wednesday = date(2026, 6, 17)
    # Monday of the same ISO week is two days before "today".
    assert periods.resolve_day('monday', today=wednesday) == '2026-06-15'


@pytest.mark.parametrize('value,expected', [
    ('monday+1', '2026-06-22'),
    ('monday-1', '2026-06-08'),
    ('friday-2', '2026-06-05'),
    ('sun+2', '2026-07-05'),
])
def test_resolve_day_weekday_offset(value, expected):
    assert periods.resolve_day(value, today=MON_2026_W25) == expected


def test_resolve_day_weekday_offset_year_rollover():
    anchor = date(2026, 1, 1)  # Thursday, ISO 2026-W01
    assert periods.resolve_day('monday-1', today=anchor) == '2025-12-22'


def test_resolve_day_rejects_garbage():
    with pytest.raises(UsageError):
        periods.resolve_day('someday', today=MON_2026_W25)
    with pytest.raises(UsageError):
        periods.resolve_day('2026-13-40', today=MON_2026_W25)


# --- month_range ------------------------------------------------------------

@pytest.mark.parametrize('year,month,expected', [
    (2026, 6, ('2026-06-01', '2026-06-30')),
    (2026, 12, ('2026-12-01', '2026-12-31')),
    (2026, 2, ('2026-02-01', '2026-02-28')),
    (2024, 2, ('2024-02-01', '2024-02-29')),  # leap year
])
def test_month_range(year, month, expected):
    assert periods.month_range(year, month) == expected


# --- resolve_window ---------------------------------------------------------

def _cal_week(week, year):
    """Mon-Sun, mirroring owa-cal."""
    monday = date.fromisocalendar(year, week, 1)
    return monday.isoformat(), (date.fromisocalendar(year, week, 7)).isoformat()


def _win(**kw):
    kw.setdefault('iso_week_range', _cal_week)
    kw.setdefault('today', MON_2026_W25)
    return periods.resolve_window(**kw)


def test_window_default_is_today():
    assert _win() == ('2026-06-15', '2026-06-15')


def test_window_date():
    assert _win(date_='tomorrow') == ('2026-06-16', '2026-06-16')


def test_window_explicit_range():
    assert _win(from_='2026-06-01', to_='2026-06-10') == ('2026-06-01', '2026-06-10')


def test_window_from_only_defaults_to_from():
    assert _win(from_='2026-06-05') == ('2026-06-05', '2026-06-05')


def test_window_week():
    assert _win(week='current') == ('2026-06-15', '2026-06-21')


def test_window_week_last():
    assert _win(week='last') == ('2026-06-08', '2026-06-14')


def test_window_month():
    assert _win(month='current') == ('2026-06-01', '2026-06-30')


def test_window_month_with_year():
    assert _win(month=3, year=2030) == ('2030-03-01', '2030-03-31')


def test_window_year_alone_is_whole_year():
    assert _win(year=2025) == ('2025-01-01', '2025-12-31')


def test_window_conflict_week_and_month():
    with pytest.raises(UsageError):
        _win(week='current', month='current')


def test_window_conflict_date_and_week():
    with pytest.raises(UsageError):
        _win(date_='today', week='current')


def test_window_conflict_range_and_period():
    with pytest.raises(UsageError):
        _win(from_='2026-06-01', week='current')
