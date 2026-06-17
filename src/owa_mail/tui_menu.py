"""Overlay menu for the owa-mail TUI — a thin adapter on the shared kit.

The generic state machine + centered-box render now live in
:mod:`owa_core.tui_kit.menu`; this module supplies owa-mail's title, top
items and settings fields, and the one mail-specific quirk: ``date_custom``
(and ``date_format == "custom"``) select to ``edit_custom`` instead of
cycling.

Actions returned by ``select()``:

    resume          Close the menu and return to the list
    quit            Exit the application
    open_settings   Navigate to the settings screen
    back            Navigate back (settings → top)
    cycle:<field>   Cycle the named setting to its next allowed value
    edit_custom     Open a text-entry prompt for ``date_custom``
    reset_settings  Restore every setting to its default value
    help            Open the help screen
    none            No-op (e.g. cursor out of range)
"""

from __future__ import annotations

from typing import Any

from owa_core.tui_kit.menu import Menu as _KitMenu

# ---------------------------------------------------------------------------
# owa-mail menu configuration
# ---------------------------------------------------------------------------

_TITLE_LINES = [
    "owa-mail",
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
    ("sort_by", "Sort by"),
    ("date_format", "Date format"),
    ("date_custom", "Date custom"),
]


def _settings_action(field: str, settings: Any) -> str:
    """Return the Action string for selecting a settings row.

    * ``date_format`` when current value is ``"custom"`` → ``edit_custom``
    * ``date_custom`` always                            → ``edit_custom``
    * everything else                                   → ``cycle:<field>``
    """
    if field == "date_custom":
        return "edit_custom"
    if field == "date_format":
        if getattr(settings, "date_format", None) == "custom":
            return "edit_custom"
    return f"cycle:{field}"


class Menu(_KitMenu):
    """owa-mail's esc-overlay menu (generic kit menu + mail field quirks)."""

    def __init__(self, screen: str = "top") -> None:
        super().__init__(_TITLE_LINES, _TOP_ITEMS, _SETTINGS_FIELDS, screen=screen)

    def _settings_action(self, field: str, settings: Any) -> str:
        return _settings_action(field, settings)
