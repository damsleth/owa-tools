"""Resolve supported Windows timezone names and IANA zones without dependencies,
and parse Microsoft's ISO-8601 timestamps."""
import re
from datetime import datetime
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
    'Greenwich Standard Time': 'Atlantic/Reykjavik',
    'Russian Standard Time': 'Europe/Moscow',
    'Turkey Standard Time': 'Europe/Istanbul',
    'Israel Standard Time': 'Asia/Jerusalem',
    'South Africa Standard Time': 'Africa/Johannesburg',
    'Arabian Standard Time': 'Asia/Dubai',
    'India Standard Time': 'Asia/Kolkata',
    'SE Asia Standard Time': 'Asia/Bangkok',
    'Singapore Standard Time': 'Asia/Singapore',
    'China Standard Time': 'Asia/Shanghai',
    'Tokyo Standard Time': 'Asia/Tokyo',
    'Korea Standard Time': 'Asia/Seoul',
    'AUS Eastern Standard Time': 'Australia/Sydney',
    'New Zealand Standard Time': 'Pacific/Auckland',
    'Atlantic Standard Time': 'America/Halifax',
    'US Mountain Standard Time': 'America/Phoenix',
    'Alaskan Standard Time': 'America/Anchorage',
    'Hawaiian Standard Time': 'Pacific/Honolulu',
    'E. South America Standard Time': 'America/Sao_Paulo',
    'Canada Central Standard Time': 'America/Regina',
}

def resolve_timezone(name):
    try:
        return ZoneInfo(WINDOWS_TZ_TO_IANA.get(name, name))
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise UsageError(f'unsupported timezone: {name!r}; use a supported Windows or IANA name') from exc


_OVERLONG_FRACTION_RE = re.compile(r'(\.\d{6})\d+')


def parse_iso_datetime(value):
    """Parse an ISO-8601 timestamp the way Python 3.10's fromisoformat can.

    Accepts a trailing ``Z`` and the 7-digit fractional seconds Outlook, Graph
    and chatsvc emit (trimmed to microseconds). Naive input stays naive.
    Raises ValueError when unparseable.
    """
    text = value.strip()
    if text[-1:] in ('Z', 'z'):
        text = text[:-1] + '+00:00'
    return datetime.fromisoformat(_OVERLONG_FRACTION_RE.sub(r'\1', text, count=1))
