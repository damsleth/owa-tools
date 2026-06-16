"""Relative / semantic period resolution for owa-tools CLIs.

Turns ergonomic period values into concrete numbers and dates so each tool
can format its own range (owa-cal uses Mon-Sun weeks, owa-sched uses Mon-Fri
work weeks, so range *formatting* stays tool-local via the ``iso_week_range``
callable passed to :func:`resolve_window`).

Stdlib only. Every "now" read goes through an injectable ``today`` argument so
callers and tests stay deterministic.

Vocabulary shared by ``--week`` / ``--month`` / ``--year``::

    current | this           the current period
    last | prev | previous   one period back
    next                     one period forward
    +n / -n                  n periods forward / back
    <bare int>               absolute period number

``--year`` is stricter: a bare unsigned value is only treated as absolute when
it is >= 100 (a real calendar year); smaller bare numbers are ambiguous and
rejected in favour of an explicit sign (``+1`` / ``-1``) or keyword.

``--date`` (see :func:`resolve_day`) additionally accepts::

    today | tomorrow | yesterday
    +n / -n                  n days forward / back
    <weekday>                that weekday in the current ISO week (Mon-anchored)
    <weekday>±n              that weekday, n weeks forward / back
    <YYYY-MM-DD>             passthrough (validated)
"""
from datetime import date, datetime, timedelta

from .errors import UsageError

_CURRENT = {'current', 'this'}
_LAST = {'last', 'prev', 'previous'}
_NEXT = {'next'}

# ISO weekday numbers (Monday = 1 ... Sunday = 7), full names + 3-letter forms.
_WEEKDAYS = {
    'monday': 1, 'mon': 1,
    'tuesday': 2, 'tue': 2, 'tues': 2,
    'wednesday': 3, 'wed': 3,
    'thursday': 4, 'thu': 4, 'thur': 4, 'thurs': 4,
    'friday': 5, 'fri': 5,
    'saturday': 6, 'sat': 6,
    'sunday': 7, 'sun': 7,
}


def _norm(value):
    return str(value if value is not None else '').strip().lower()


def _today(today):
    return today or date.today()


def _parse_relative(value, flag):
    """Parse a shared-vocabulary period value.

    Returns ``('abs', n)`` for an absolute period number or ``('rel', n)`` for
    a signed offset (keywords map to -1/0/+1). Raises UsageError otherwise.
    """
    v = _norm(value)
    if v in _CURRENT:
        return 'rel', 0
    if v in _LAST:
        return 'rel', -1
    if v in _NEXT:
        return 'rel', 1
    if v and v[0] in '+-':
        try:
            return 'rel', int(v)
        except ValueError:
            raise UsageError(f'{flag}: invalid offset: {value!r}')
    try:
        return 'abs', int(v)
    except ValueError:
        raise UsageError(
            f'{flag}: expected a number, a signed offset (+1/-1), or one of '
            f'current/last/next; got {value!r}'
        )


def resolve_week(value, *, today=None, year=None):
    """Resolve a ``--week`` value to ``(iso_year, iso_week)``.

    ``year`` (already resolved to an int) overrides the year only for an
    absolute week number; it is meaningless for a relative offset and ignored
    there.
    """
    base = _today(today)
    kind, n = _parse_relative(value, '--week')
    if kind == 'abs':
        iso_year = year if year is not None else base.isocalendar()[0]
        if not 1 <= n <= 53:
            raise UsageError(f'--week: week number out of range (1-53): {n}')
        try:
            date.fromisocalendar(iso_year, n, 1)
        except ValueError:
            raise UsageError(f'--week: {iso_year} has no week {n}')
        return iso_year, n
    iso = base.isocalendar()
    monday = date.fromisocalendar(iso[0], iso[1], 1) + timedelta(weeks=n)
    shifted = monday.isocalendar()
    return shifted[0], shifted[1]


def resolve_month(value, *, today=None, year=None):
    """Resolve a ``--month`` value to ``(year, month)``."""
    base = _today(today)
    kind, n = _parse_relative(value, '--month')
    if kind == 'abs':
        if not 1 <= n <= 12:
            raise UsageError(f'--month: month number out of range (1-12): {n}')
        return (year if year is not None else base.year), n
    idx = base.year * 12 + (base.month - 1) + n
    return idx // 12, idx % 12 + 1


def resolve_year(value, *, today=None):
    """Resolve a ``--year`` value to an int.

    Bare unsigned values are absolute only when >= 100; smaller bare numbers
    are rejected as ambiguous.
    """
    base = _today(today)
    v = _norm(value)
    if v in _CURRENT:
        return base.year
    if v in _LAST:
        return base.year - 1
    if v in _NEXT:
        return base.year + 1
    if v and v[0] in '+-':
        try:
            return base.year + int(v)
        except ValueError:
            raise UsageError(f'--year: invalid offset: {value!r}')
    try:
        n = int(v)
    except ValueError:
        raise UsageError(
            f'--year: expected a full year (e.g. 2026), a signed offset '
            f'(+1/-1), or one of current/last/next; got {value!r}'
        )
    if n >= 100:
        return n
    raise UsageError(
        f'--year: bare value {n} is ambiguous; use a full year (e.g. 2026) '
        f'or a signed offset (+{n}/-{n})'
    )


def _split_weekday(v):
    """Split ``mondaY+1`` into (iso_weekday, weeks). Returns (None, 0) on no
    match."""
    name, weeks = v, 0
    for i, ch in enumerate(v):
        if ch in '+-':
            suffix = v[i:]
            if not suffix[1:].isdigit():
                return None, 0
            name, weeks = v[:i], int(suffix)
            break
    wd = _WEEKDAYS.get(name)
    if wd is None:
        return None, 0
    return wd, weeks


def resolve_day(value, *, today=None):
    """Resolve a ``--date`` value to a ``YYYY-MM-DD`` string."""
    base = _today(today)
    v = _norm(value)
    if v in ('', 'today'):
        return base.isoformat()
    if v == 'tomorrow':
        return (base + timedelta(days=1)).isoformat()
    if v == 'yesterday':
        return (base - timedelta(days=1)).isoformat()
    if v[0] in '+-' and v[1:].isdigit():
        return (base + timedelta(days=int(v))).isoformat()
    wd, weeks = _split_weekday(v)
    if wd is not None:
        iso = base.isocalendar()
        target = date.fromisocalendar(iso[0], iso[1], wd) + timedelta(weeks=weeks)
        return target.isoformat()
    try:
        return datetime.strptime(v, '%Y-%m-%d').date().isoformat()
    except ValueError:
        raise UsageError(
            f'--date: expected YYYY-MM-DD, today/tomorrow/yesterday, a signed '
            f'day offset (+1/-3), or a weekday name (monday[, monday+1]); '
            f'got {value!r}'
        )


def month_range(year, month):
    """Return ``(first_iso, last_iso)`` for a calendar month."""
    first = date(year, month, 1)
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first.isoformat(), (nxt - timedelta(days=1)).isoformat()


def resolve_window(*, iso_week_range, date_=None, from_=None, to_=None,
                   week=None, month=None, year=None, today=None):
    """Resolve event-listing flags to an inclusive ``(from_iso, to_iso)``.

    Precedence: explicit ``--from/--to`` > ``--date`` > ``--week`` > ``--month``
    > ``--year`` (whole year) > today. Combining selectors from different tiers
    is a usage error; ``--year`` may accompany ``--week`` or ``--month`` (as the
    year) but not ``--date`` or ``--from/--to``.

    ``iso_week_range(week, year) -> (from_iso, to_iso)`` is supplied by the
    caller so each tool keeps its own week shape (Mon-Sun vs Mon-Fri).
    """
    has_range = bool(from_ or to_)
    has_date = bool(date_)
    has_week = bool(week)
    has_month = bool(month)
    has_year = bool(year)

    if has_range and (has_date or has_week or has_month or has_year):
        raise UsageError('--from/--to cannot be combined with '
                         '--date/--week/--month/--year')
    if has_date and (has_week or has_month or has_year):
        raise UsageError('--date cannot be combined with --week/--month/--year')
    if has_week and has_month:
        raise UsageError('conflicting period flags: --week and --month')

    if has_range:
        f = resolve_day(from_, today=today) if from_ else _today(today).isoformat()
        t = resolve_day(to_, today=today) if to_ else f
        return f, t

    if has_date:
        d = resolve_day(date_, today=today)
        return d, d

    year_val = resolve_year(year, today=today) if has_year else None

    if has_week:
        y, w = resolve_week(week, today=today, year=year_val)
        return iso_week_range(w, y)

    if has_month:
        y, m = resolve_month(month, today=today, year=year_val)
        return month_range(y, m)

    if has_year:
        return month_range(year_val, 1)[0], month_range(year_val, 12)[1]

    d = _today(today).isoformat()
    return d, d
