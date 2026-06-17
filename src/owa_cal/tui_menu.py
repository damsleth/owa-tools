"""Overlay menu for the owa-cal TUI — a thin adapter on the shared kit.

The generic state machine + centered-box render live in
:mod:`owa_core.tui_kit.menu`; this module supplies owa-cal's title, top
items and settings fields.

Actions returned by ``select()``:

    resume          Close the menu and return to the list
    quit            Exit the application
    open_settings   Navigate to the settings screen
    back            Navigate back (settings -> top)
    cycle:<field>   Cycle the named setting to its next allowed value
    reset_settings  Restore every setting to its default value
    none            No-op (e.g. cursor out of range)
"""

from __future__ import annotations

from owa_core.tui_kit.menu import Menu as _KitMenu

# ---------------------------------------------------------------------------
# owa-cal menu configuration
# ---------------------------------------------------------------------------

_TITLE_LINES = [
    "owa-cal",
    "─" * 16,
]

_TOP_ITEMS: list[tuple[str, str]] = [
    ("Resume", "resume"),
    ("Settings", "open_settings"),
    ("Help", "help"),
    ("Quit", "quit"),
]

# (field, label) in display order; values are read off the Settings object.
_SETTINGS_FIELDS: list[tuple[str, str]] = [
    ("reading_pane", "Reading pane"),
    ("split_ratio", "Split ratio"),
    ("day_range", "Day range"),
    ("show_declined", "Show declined"),
    ("event_detail", "Event detail"),
]


class Menu(_KitMenu):
    """owa-cal's esc-overlay menu (generic kit menu with cal-specific fields)."""

    def __init__(self, screen: str = "top") -> None:
        super().__init__(_TITLE_LINES, _TOP_ITEMS, _SETTINGS_FIELDS, screen=screen)
