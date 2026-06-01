"""Client-side message sorting for the owa-mail TUI.

Pure functions only — no curses, no network, no I/O. Each function returns
a new list; the input is never mutated. All sorts are stable (Python's sort
is guaranteed stable). Missing or None fields sort last / treated as ''.
"""

from __future__ import annotations

_SORT_KEYS = frozenset({"date_desc", "date_asc", "sender", "subject", "unread_first"})


def sort_messages(messages: list[dict], sort_by: str) -> list[dict]:
    """Return a new list of messages sorted by *sort_by*.

    Supported values for *sort_by*:
        date_desc      — newest first (by ``received``)
        date_asc       — oldest first (by ``received``)
        sender         — A-Z by ``from``, case-insensitive; missing → last
        subject        — A-Z by ``subject``, case-insensitive; missing → last
        unread_first   — unread messages first, then newest-first within each group

    Any unknown *sort_by* value falls back to ``date_desc``.
    Missing or None fields never raise; they sort last (or as empty string).
    """
    if sort_by not in _SORT_KEYS:
        sort_by = "date_desc"

    if sort_by == "date_desc":
        # reverse=True on (present, received): real dates sort newest-first and
        # missing entries (present=0) fall to the end.
        return sorted(messages, key=_key_date_desc, reverse=True)

    if sort_by == "date_asc":
        # ascending on (missing, received): real dates sort oldest-first and
        # missing entries (missing=1) still fall to the end.
        return sorted(messages, key=_key_date_asc)

    if sort_by == "sender":
        return sorted(messages, key=_key_sender)

    if sort_by == "subject":
        return sorted(messages, key=_key_subject)

    # sort_by == "unread_first"
    return sorted(messages, key=_key_unread_first)


# ---------------------------------------------------------------------------
# Key functions
# ---------------------------------------------------------------------------

def _key_date_desc(msg: dict) -> tuple[int, str]:
    """Sort key for date_desc, used with ``reverse=True``: ``(present, received)``.

    Present dates get ``present=1`` and missing/None get ``(0, "")``. Under
    ``reverse=True`` the real dates sort newest-first and the missing entries
    (present=0) sink to the bottom — so missing always sorts last."""
    val = msg.get("received")
    if not val:
        return (0, "")
    return (1, val)


def _key_date_asc(msg: dict) -> tuple[int, str]:
    """Sort key for date_asc, used with the default ascending sort:
    ``(missing, received)``.

    Present dates get ``missing=0`` and missing/None get ``(1, "")``. Ascending,
    real dates sort oldest-first and the missing entries (missing=1) stay at the
    bottom — so missing sorts last in this direction too."""
    val = msg.get("received")
    if not val:
        return (1, "")
    return (0, val)


def _key_sender(msg: dict) -> tuple[int, str]:
    """Sort key for sender: (has_value, casefold).  Missing/None → (1, '')
    so they sort after all real senders."""
    val = msg.get("from")
    if not val:
        return (1, "")
    return (0, val.casefold())


def _key_subject(msg: dict) -> tuple[int, str]:
    """Sort key for subject: (has_value, casefold).  Missing/None → (1, '')."""
    val = msg.get("subject")
    if not val:
        return (1, "")
    return (0, val.casefold())


def _key_unread_first(msg: dict) -> tuple[int, str]:
    """Sort key for unread-first: (is_read_int, neg-received).

    Unread (is_read=False/None) → group 0; read → group 1.
    Within each group, newest first (received descending).  We invert the
    received string with a leading '~' trick: '~' > any digit/letter in
    ASCII, so subtracting is not needed — instead we negate the sort for the
    received part by sorting the whole tuple ascending but putting a
    tilde-prefixed complement as the secondary key.

    Simpler implementation: use a large constant minus a numeric date is
    fragile.  We rely on the fact that ISO 8601 strings sort lexicographically
    and flip them by using a descending secondary sort via a wrapper.
    """
    is_read = msg.get("is_read")
    # Treat None / missing as unread (group 0, same as False)
    read_group = 1 if is_read else 0
    received = msg.get("received") or ""
    # We want newest-first within each group: higher date = earlier in output.
    # Since we sort the outer list ascending, invert the received string.
    # ISO strings are comparable; we negate by wrapping in a _Desc helper.
    return (read_group, _Desc(received))


class _Desc:
    """Wrapper that reverses comparison order for a string.

    Used so we can sort ascending on the outer key tuple while sorting
    descending on just the ``received`` component.
    """

    __slots__ = ("_val",)

    def __init__(self, val: str) -> None:
        self._val = val

    def __lt__(self, other: "_Desc") -> bool:
        return self._val > other._val

    def __le__(self, other: "_Desc") -> bool:
        return self._val >= other._val

    def __gt__(self, other: "_Desc") -> bool:
        return self._val < other._val

    def __ge__(self, other: "_Desc") -> bool:
        return self._val <= other._val

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _Desc):
            return NotImplemented
        return self._val == other._val

    def __repr__(self) -> str:
        return f"_Desc({self._val!r})"
