"""Pure, terminal-agnostic layout helpers shared by owa-* TUIs.

No curses, no I/O — just geometry and text fitting, so they are trivially
unit-testable. Lifted from owa-mail's TUI so every tool splits the screen,
pads, truncates and wraps identically.

    regions(width, height, placement, ratio) -> Regions
        Compute the list-rect and detail-pane rect for one frame.
    wrap_body(text, width) -> list[str]
        Hard-wrap text for a reading/detail pane (blank lines preserved).
    pad(s, width) -> str
        Left-justify to exactly ``width`` (truncates if longer).
    truncate(s, n) -> str
        Hard-truncate to at most ``n`` chars (no ellipsis).
    truncate_ellipsis(s, n) -> str
        Truncate to ``n`` chars, marking elision with ``…``.
"""
from __future__ import annotations

import textwrap
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------

PLACEMENT_OFF = "off"
PLACEMENT_RIGHT = "right"
PLACEMENT_BOTTOM = "bottom"

_VALID_PLACEMENTS = {PLACEMENT_OFF, PLACEMENT_RIGHT, PLACEMENT_BOTTOM}
_VALID_RATIOS = {40, 50, 60}


class Rect(NamedTuple):
    """A rectangular region: position + size."""

    x: int
    y: int
    w: int
    h: int


class Regions(NamedTuple):
    """Computed layout for one terminal frame."""

    list_rect: Rect
    pane_rect: Rect  # (0,0,0,0) when placement is 'off'


def regions(
    width: int,
    height: int,
    placement: str,
    ratio: int,
) -> Regions:
    """Return list and pane rects for (width, height, placement, ratio).

    Parameters
    ----------
    width, height : terminal dimensions (columns, rows)
    placement     : 'off' | 'right' | 'bottom'
    ratio         : list percentage — 40, 50, or 60

    The divider is always 1 col (right) or 1 row (bottom).
    Negative or zero dimensions are clamped to 0 so tiny terminals never
    produce invalid geometry.
    """
    if placement not in _VALID_PLACEMENTS:
        placement = PLACEMENT_OFF
    if ratio not in _VALID_RATIOS:
        ratio = 50

    w = max(width, 0)
    h = max(height, 0)

    if placement == PLACEMENT_OFF:
        return Regions(
            list_rect=Rect(x=0, y=0, w=w, h=h),
            pane_rect=Rect(x=0, y=0, w=0, h=0),
        )

    if placement == PLACEMENT_RIGHT:
        # side-by-side with a 1-column divider
        list_w = max(int(w * ratio / 100), 0)
        divider = 1 if w > 1 else 0
        pane_x = list_w + divider
        pane_w = max(w - list_w - divider, 0)
        return Regions(
            list_rect=Rect(x=0, y=0, w=list_w, h=h),
            pane_rect=Rect(x=pane_x, y=0, w=pane_w, h=h),
        )

    # placement == PLACEMENT_BOTTOM
    # stacked with a 1-row divider
    list_h = max(int(h * ratio / 100), 0)
    divider = 1 if h > 1 else 0
    pane_y = list_h + divider
    pane_h = max(h - list_h - divider, 0)
    return Regions(
        list_rect=Rect(x=0, y=0, w=w, h=list_h),
        pane_rect=Rect(x=0, y=pane_y, w=w, h=pane_h),
    )


# ---------------------------------------------------------------------------
# Text fitting
# ---------------------------------------------------------------------------


def pad(s: str, width: int) -> str:
    """Left-justify *s* to exactly *width* characters (truncate if longer)."""
    if len(s) >= width:
        return s[:width]
    return s + ' ' * (width - len(s))


def truncate(s: str, n: int) -> str:
    """Hard-truncate *s* to at most *n* characters (no ellipsis)."""
    if n <= 0:
        return ''
    return s[:n]


def truncate_ellipsis(s: str, n: int) -> str:
    """Truncate *s* to *n* characters, marking elision with ``…``."""
    if n <= 0:
        return ''
    if len(s) <= n:
        return s
    if n == 1:
        return s[0]
    return s[: n - 1] + "…"


def wrap_body(text: str, width: int) -> list[str]:
    """Hard-wrap plain text to ``width`` columns for a reading/detail pane.

    Preserves blank lines and wraps long lines (including footnote URLs).
    Returns an empty list for empty input.
    """
    if not text:
        return []
    width = max(width, 1)
    out: list[str] = []
    for raw in text.split("\n"):
        if not raw.strip():
            out.append("")
            continue
        out.extend(
            textwrap.wrap(
                raw,
                width,
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [""]
        )
    return out
