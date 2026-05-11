"""Shared text-rendering helpers for pretty output across the suite."""


def pad(s, width):
    """Right-pad with spaces to `width`. Returns `s` as-is if longer."""
    s = str(s) if s is not None else ''
    if len(s) >= width:
        return s
    return s + ' ' * (width - len(s))


def truncate(s, n, suffix='…'):
    """Truncate `s` to fit in `n` chars, appending `suffix` (default `…`)
    when the source was longer than `n`."""
    s = str(s) if s is not None else ''
    if len(s) <= n:
        return s
    if n <= len(suffix):
        return suffix[:n]
    return s[: n - len(suffix)] + suffix


def date_part(iso):
    """Take the YYYY-MM-DD prefix from an ISO datetime string."""
    return iso.split('T')[0] if iso else ''


def time_part(iso):
    """Take HH:MM from the time portion of an ISO datetime string."""
    if not iso or 'T' not in iso:
        return ''
    return ':'.join(iso.split('T')[1].split(':')[:2])
