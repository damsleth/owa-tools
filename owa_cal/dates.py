"""Date/time helpers for CLI argument parsing.

All "friendly" resolutions happen here so the rest of the code only
deals with YYYY-MM-DD strings and ISO datetime strings.
"""
from datetime import date, datetime, timedelta


def today():
    return date.today().strftime('%Y-%m-%d')


def tomorrow():
    return (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')


def yesterday():
    return (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')


def resolve_date(value):
    """Map today/tomorrow/yesterday to an ISO date; pass anything else
    through untouched."""
    if value == 'today':
        return today()
    if value == 'tomorrow':
        return tomorrow()
    if value == 'yesterday':
        return yesterday()
    return value


def iso_week_range(week, year):
    """Monday and Sunday (YYYY-MM-DD) for an ISO week."""
    week = int(week)
    year = int(year)
    monday = datetime.strptime(f'{year}-W{week:02d}-1', '%G-W%V-%u')
    sunday = monday + timedelta(days=6)
    return monday.strftime('%Y-%m-%d'), sunday.strftime('%Y-%m-%d')


def make_datetime(date_val, time_val=''):
    """Combine YYYY-MM-DD with HH:MM[:SS] -> YYYY-MM-DDTHH:MM:SS.

    If date_val already contains a T, it is returned unchanged. If
    time_val is empty, midnight is used.
    """
    if time_val:
        # HH:MM or HH:MM:SS
        parts = time_val.split(':')
        if len(parts) == 2:
            return f'{date_val}T{time_val}:00'
        return f'{date_val}T{time_val}'
    if 'T' in date_val:
        return date_val
    return f'{date_val}T00:00:00'


def current_iso_week():
    """Returns (week, year) for today."""
    today_dt = date.today()
    iso = today_dt.isocalendar()
    # isocalendar() returns (year, week, weekday) on 3.9+, a namedtuple
    # on older; handle both.
    try:
        return iso.week, iso.year
    except AttributeError:
        return iso[1], iso[0]
