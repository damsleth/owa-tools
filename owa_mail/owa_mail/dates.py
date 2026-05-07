"""Date helpers for CLI argument parsing.

All "friendly" resolutions happen here so the rest of the code only
deals with YYYY-MM-DD strings.
"""
from datetime import date, timedelta


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
