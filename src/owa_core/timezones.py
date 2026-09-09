"""Resolve supported Windows timezone names and IANA zones without dependencies."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import UsageError

WINDOWS_TZ_TO_IANA = {
    'UTC': 'UTC',
    'W. Europe Standard Time': 'Europe/Berlin',
    'Romance Standard Time': 'Europe/Paris',
    'Central European Standard Time': 'Europe/Warsaw',
    'Central Europe Standard Time': 'Europe/Budapest',
    'E. Europe Standard Time': 'Europe/Bucharest',
    'FLE Standard Time': 'Europe/Helsinki',
    'GTB Standard Time': 'Europe/Athens',
    'GMT Standard Time': 'Europe/London',
    'Eastern Standard Time': 'America/New_York',
    'Pacific Standard Time': 'America/Los_Angeles',
    'Mountain Standard Time': 'America/Denver',
    'Central Standard Time': 'America/Chicago',
}

def resolve_timezone(name):
    try:
        return ZoneInfo(WINDOWS_TZ_TO_IANA.get(name, name))
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise UsageError(f'unsupported timezone: {name!r}; use a supported Windows or IANA name') from exc
