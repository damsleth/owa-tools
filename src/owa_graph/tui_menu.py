"""Esc-overlay menu for the owa-graph interactive explorer.

Builds on the shared :class:`owa_core.tui_kit.menu.Menu` base, so drawing,
navigation and the settings-cycle mechanics are inherited. The graph menu
adds the Audiences, Bookmarks and Help top items, and wires the seven
graph-specific settings fields through the kit's generic cycle/reset flow.

Top-level items (action strings returned by ``Menu.select``):
    ``resume``         — close the overlay, return to the list
    ``open_audiences`` — audience switcher overlay
    ``open_settings``  — settings screen
    ``open_bookmarks`` — bookmarks overlay
    ``open_help``      — help overlay
    ``quit``           — exit the TUI

DO NOT import owa_mail.tui_menu.
"""
from __future__ import annotations

from owa_core.tui_kit.menu import Menu as _Menu

# ---------------------------------------------------------------------------
# Settings field meta (label shown in the settings screen)
# ---------------------------------------------------------------------------

_SETTINGS_FIELDS = [
    ('reading_pane',    'Reading pane'),
    ('split_ratio',     'Split ratio'),
    ('pretty_json',     'Pretty JSON'),
    ('scope_warnings',  'Scope warnings'),
    ('default_audience', 'Default audience'),
    ('default_path',    'Default path'),
    ('bookmarks',       'Bookmarks JSON'),
]

_TITLE_LINES = ['owa-graph', '─' * 16]

_TOP_ITEMS = [
    ('Resume',     'resume'),
    ('Audiences',  'open_audiences'),
    ('Settings',   'open_settings'),
    ('Bookmarks',  'open_bookmarks'),
    ('Help',       'open_help'),
    ('Quit',       'quit'),
]


# ---------------------------------------------------------------------------
# Graph menu subclass
# ---------------------------------------------------------------------------

class GraphMenu(_Menu):
    """Menu subclass that routes custom top-level actions to the caller.

    ``select`` returns the raw action string; the graph BrowserSpec's
    ``on_menu_action`` callback receives it and decides what overlay to
    open. The kit loop handles ``resume`` / ``open_settings`` / ``back`` /
    ``quit`` internally, so those never reach ``on_menu_action``.
    """

    def _settings_action(self, field: str, settings) -> str:
        # graph has only cycled fields + free-text (no custom sub-actions);
        # delegate entirely to the base-class default.
        return super()._settings_action(field, settings)


def build_menu() -> GraphMenu:
    """Return the configured owa-graph menu instance."""
    return GraphMenu(
        title_lines=_TITLE_LINES,
        top_items=_TOP_ITEMS,
        settings_fields=_SETTINGS_FIELDS,
    )
