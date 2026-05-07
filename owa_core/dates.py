"""Date and timezone helpers. zoneinfo-first; static-table fallback.

Public surface:
    parse(s: str, *, default_tz) -> datetime
    iso_week(year: int, week: int) -> tuple[date, date]
    resolve_tz(name: str | None) -> tzinfo

Replaces hand-rolled DST math in owa-cal/owa-mail/owa-sched.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    _ZONEINFO = True
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment, misc]
    _ZONEINFO = False

from .errors import UsageError


# Windows -> IANA mapping for the zones the suite is most likely to see.
# Not exhaustive: extend on demand. The point is to cover the cases that
# Outlook/Graph hand back without forcing every consumer to ship its own
# table.
_WINDOWS_TO_IANA = {
    "UTC": "UTC",
    "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Europe/London",
    "W. Europe Standard Time": "Europe/Berlin",
    "Central Europe Standard Time": "Europe/Budapest",
    "Romance Standard Time": "Europe/Paris",
    "Central European Standard Time": "Europe/Warsaw",
    "Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "Pacific Standard Time": "America/Los_Angeles",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "Tokyo Standard Time": "Asia/Tokyo",
    "China Standard Time": "Asia/Shanghai",
    "India Standard Time": "Asia/Kolkata",
    "FLE Standard Time": "Europe/Helsinki",
    "Russian Standard Time": "Europe/Moscow",
}


def resolve_tz(name: str | None) -> tzinfo:
    """Return a tzinfo for an IANA name, Windows zone name, or None.

    None resolves to UTC. Windows zone names are mapped through a small
    static table. If zoneinfo is unavailable or the name is unknown,
    falls back to UTC rather than raising.
    """
    if not name:
        return timezone.utc
    iana = _WINDOWS_TO_IANA.get(name, name)
    if not _ZONEINFO:
        return timezone.utc
    try:
        return ZoneInfo(iana)
    except ZoneInfoNotFoundError:
        return timezone.utc


def parse(s: str, *, default_tz: tzinfo | str | None = None) -> datetime:
    """Parse an ISO-ish datetime string. Naive results adopt default_tz.

    Accepts:
        - 'YYYY-MM-DD'
        - 'YYYY-MM-DDTHH:MM[:SS[.ffffff]][Z|+HH:MM]'
        - Same with a space instead of 'T'
    """
    if not isinstance(s, str) or not s.strip():
        raise UsageError("empty datetime string")
    txt = s.strip().replace(" ", "T")
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        if "T" in txt:
            dt = datetime.fromisoformat(txt)
        else:
            dt = datetime.fromisoformat(txt + "T00:00:00")
    except ValueError as e:
        raise UsageError(f"invalid datetime: {s!r}: {e}") from e
    if dt.tzinfo is None:
        tz = default_tz if isinstance(default_tz, tzinfo) else resolve_tz(
            default_tz if isinstance(default_tz, str) else None
        )
        dt = dt.replace(tzinfo=tz)
    return dt


def iso_week(year: int, week: int) -> tuple[date, date]:
    """Monday/Sunday bounds for an ISO 8601 (year, week) pair."""
    if not (1 <= week <= 53):
        raise UsageError(f"invalid ISO week: {week}")
    try:
        monday = date.fromisocalendar(year, week, 1)
    except ValueError as e:
        raise UsageError(str(e)) from e
    return monday, monday + timedelta(days=6)
