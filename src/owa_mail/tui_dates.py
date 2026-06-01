"""Date formatting helpers for the owa-mail TUI.

Pure stdlib — no curses, no network, no I/O.

Public API
----------
format_received(iso, fmt, custom='') -> str
    Format an ISO 8601 datetime string according to *fmt*.

validate_custom_format(s) -> bool
    Return True iff *s* is a non-empty, safe strftime format string.
"""

from __future__ import annotations

from datetime import datetime

# ---------------------------------------------------------------------------
# Supported format keys
# ---------------------------------------------------------------------------

_FMT_ISO8601 = "iso8601"
_FMT_DDMM = "ddmm"
_FMT_DDMM_HHMM = "ddmm_hhmm"
_FMT_CUSTOM = "custom"

_SUPPORTED_FMTS = frozenset({_FMT_ISO8601, _FMT_DDMM, _FMT_DDMM_HHMM, _FMT_CUSTOM})

# A fixed sample datetime used when validating a custom strftime string.
_VALIDATE_SAMPLE = datetime(2000, 1, 2, 3, 4, 5)


# ---------------------------------------------------------------------------
# ISO parsing
# ---------------------------------------------------------------------------


def _parse_iso(iso: str) -> datetime | None:
    """Parse an ISO 8601-ish datetime string defensively.

    Handles:
    - ``YYYY-MM-DDTHH:MM:SS`` (with or without trailing ``Z`` / offset)
    - ``YYYY-MM-DD`` (date only)
    - Leading/trailing whitespace

    Returns ``None`` on any parse failure rather than raising.
    """
    s = iso.strip()
    if not s:
        return None

    # Strip trailing Z (UTC marker) or simple numeric offset (+HH:MM / -HH:MM).
    # We treat the stored value as wall-clock; no tz conversion needed.
    if s.endswith("Z"):
        s = s[:-1]

    # Strip a fixed-offset suffix like +02:00 or -05:30
    if len(s) > 19 and s[19] in ("+", "-"):
        s = s[:19]

    # Try full datetime first, then date-only
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)  # noqa: DTZ007
        except ValueError:
            continue

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_received(iso: str, fmt: str, custom: str = "") -> str:
    """Return *iso* formatted according to *fmt*.

    Parameters
    ----------
    iso:
        An ISO 8601 datetime string (e.g. ``'2026-05-11T09:30:00Z'``).
        Empty string or unparseable input returns ``''``.
    fmt:
        One of ``'iso8601'``, ``'ddmm'``, ``'ddmm_hhmm'``, ``'custom'``.
        Unknown values fall back to ``'iso8601'``.
    custom:
        A strftime format string used when *fmt* is ``'custom'``.
        Ignored for other *fmt* values.

    Returns
    -------
    str
        Formatted date string, or ``''`` if *iso* is empty / unparseable.
    """
    if not iso or not iso.strip():
        return ""

    dt = _parse_iso(iso)
    if dt is None:
        return ""

    if fmt == _FMT_DDMM:
        return dt.strftime("%d.%m")

    if fmt == _FMT_DDMM_HHMM:
        return dt.strftime("%d.%m %H:%M")

    if fmt == _FMT_CUSTOM:
        if not custom:
            # No custom format provided — fall back to iso8601
            return dt.strftime("%Y-%m-%d")
        try:
            return dt.strftime(custom)
        except (ValueError, TypeError):
            return ""

    # Default: iso8601 (also catches unknown fmt values)
    return dt.strftime("%Y-%m-%d")


def validate_custom_format(s: str) -> bool:
    """Return ``True`` iff *s* is a non-empty, safe strftime format string.

    Validation strategy: attempt to format a fixed sample datetime with *s*.
    An empty string or any string that causes ``strftime`` to raise is
    considered invalid.
    """
    if not s or not s.strip():
        return False
    try:
        result = _VALIDATE_SAMPLE.strftime(s)
        # strftime always returns a string; just make sure it didn't produce
        # something clearly wrong (e.g. empty output from a whitespace-only fmt).
        return bool(result)
    except (ValueError, TypeError):
        return False
