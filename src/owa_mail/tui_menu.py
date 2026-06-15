"""Overlay menu state machine for the owa-mail TUI.

Pure module (no curses, no I/O).  The integration agent blits the lines
returned by ``Menu.render()`` onto the screen using ``_safe_addstr``.

Screen hierarchy
----------------
``top``       Resume / Settings / Help / Quit
``settings``  One row per setting  (label: current value)  + Back

Actions
-------
Strings returned by ``select()``:

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

# ---------------------------------------------------------------------------
# Dependency on tui_settings (U5 — may land in parallel)
# ---------------------------------------------------------------------------
# We import lazily so that the module can be imported even when tui_settings
# has not been created yet.  The *render* and *select* methods call
# _get_settings_meta() which will raise clearly if the dependency is missing.

_SETTINGS_META: list[dict[str, Any]] | None = None


def _get_settings_meta() -> list[dict[str, Any]]:
    """Return ordered field metadata from tui_settings.

    Each entry is a dict::

        {
            "field":  str,       # attribute name on Settings
            "label":  str,       # human-readable label
            "custom": bool,      # True iff selecting this row returns edit_custom
        }

    The ``custom`` flag is set when the setting is ``date_format`` *and* the
    current value is ``"custom"``, signalling that the host should open a
    text prompt for the raw strftime pattern instead of cycling.
    """
    global _SETTINGS_META
    if _SETTINGS_META is not None:
        return _SETTINGS_META

    try:
        from owa_mail import tui_settings as _ts  # noqa: PLC0415

        meta = []
        for field in ("reading_pane", "split_ratio", "sort_by", "date_format", "date_custom"):
            label_map = {
                "reading_pane": "Reading pane",
                "split_ratio": "Split ratio",
                "sort_by": "Sort by",
                "date_format": "Date format",
                "date_custom": "Date custom",
            }
            meta.append(
                {
                    "field": field,
                    "label": label_map[field],
                    "module": _ts,
                }
            )
        _SETTINGS_META = meta
        return _SETTINGS_META
    except ImportError:
        # tui_settings not yet available; fall back to a static list so the
        # module is importable and tests can inject their own settings objects.
        return _STATIC_SETTINGS_META


# Static fallback metadata used when tui_settings is not installed yet.
# Tests that want full field cycling must supply a settings object whose
# attributes match these field names.
_STATIC_SETTINGS_META: list[dict[str, Any]] = [
    {"field": "reading_pane", "label": "Reading pane", "module": None},
    {"field": "split_ratio", "label": "Split ratio", "module": None},
    {"field": "sort_by", "label": "Sort by", "module": None},
    {"field": "date_format", "label": "Date format", "module": None},
    {"field": "date_custom", "label": "Date custom", "module": None},
]

# ---------------------------------------------------------------------------
# Top-level menu items
# ---------------------------------------------------------------------------

_TOP_ITEMS: list[tuple[str, str]] = [
    ("Resume", "resume"),
    ("Settings", "open_settings"),
    ("Help", "help"),
    ("Quit", "quit"),
]

# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------

_SETTINGS_FIELDS_WITH_CUSTOM_PATH = {"date_format", "date_custom"}


def _settings_action(field: str, settings: Any) -> str:
    """Return the Action string for selecting a settings row.

    * ``date_format`` when current value is ``"custom"`` → ``edit_custom``
    * ``date_custom`` always                            → ``edit_custom``
    * everything else                                   → ``cycle:<field>``
    """
    if field == "date_custom":
        return "edit_custom"
    if field == "date_format":
        current = getattr(settings, "date_format", None)
        if current == "custom":
            return "edit_custom"
    return f"cycle:{field}"


# ---------------------------------------------------------------------------
# Menu state machine
# ---------------------------------------------------------------------------


class Menu:
    """Pure overlay-menu state machine.

    Parameters
    ----------
    screen:
        Starting screen – ``"top"`` or ``"settings"``.
    """

    def __init__(self, screen: str = "top") -> None:
        self._screen: str = screen
        self._cursor: int = 0

    # ------------------------------------------------------------------ props

    @property
    def screen(self) -> str:
        return self._screen

    @property
    def cursor(self) -> int:
        return self._cursor

    # ------------------------------------------------------------------ items

    def _items(self) -> list[tuple[str, str]]:
        """Return (display_label, raw_action) for the current screen.

        For the ``settings`` screen the display label includes the current
        value and the raw_action is a placeholder; ``select()`` builds the
        final Action after inspecting the settings object.
        """
        if self._screen == "top":
            return list(_TOP_ITEMS)
        # settings screen: placeholder action; resolved in select()
        meta = _get_settings_meta()
        return ([(m["label"], m["field"]) for m in meta]
                + [("Reset to defaults", "reset"), ("Back", "back")])

    def items_for_settings(self, settings: Any) -> list[str]:
        """Return display labels for the settings screen (includes current values)."""
        meta = _get_settings_meta()
        rows: list[str] = []
        for m in meta:
            field = m["field"]
            value = getattr(settings, field, "")
            rows.append(f"{m['label']}: {value}")
        rows.append("Reset to defaults")
        rows.append("Back")
        return rows

    # ---------------------------------------------------------------- nav

    def move(self, delta: int) -> None:
        """Move the cursor by *delta* rows, clamping to [0, len-1]."""
        items = self._items()
        n = len(items)
        if n == 0:
            self._cursor = 0
            return
        self._cursor = max(0, min(n - 1, self._cursor + delta))

    def move_wrap(self, delta: int) -> None:
        """Move the cursor by *delta* rows, wrapping around."""
        items = self._items()
        n = len(items)
        if n == 0:
            self._cursor = 0
            return
        self._cursor = (self._cursor + delta) % n

    # ---------------------------------------------------------------- actions

    def select(self, settings: Any | None = None) -> str:
        """Return the Action for the currently highlighted item.

        Parameters
        ----------
        settings:
            Current ``Settings`` instance – required for the settings screen
            so that the correct action (cycle vs. edit_custom) can be
            determined.  Pass ``None`` on the top screen (not needed).
        """
        items = self._items()
        if not items or self._cursor >= len(items):
            return "none"

        if self._screen == "top":
            _, action = items[self._cursor]
            return action

        # settings screen
        label, field = items[self._cursor]
        if field == "back":
            return "back"
        if field == "reset":
            return "reset_settings"
        if settings is None:
            # No settings object – fall back to cycle
            return f"cycle:{field}"
        return _settings_action(field, settings)

    def back(self) -> None:
        """Navigate one level back (settings → top; top stays at top)."""
        if self._screen == "settings":
            self._screen = "top"
            self._cursor = 0
        # on top screen, back is a no-op (host handles esc→close)

    def open_settings(self) -> None:
        """Navigate to the settings screen."""
        self._screen = "settings"
        self._cursor = 0

    # ---------------------------------------------------------------- render

    def render(self, width: int, height: int, settings: Any) -> list[str]:
        """Render the overlay menu as a list of left-padded strings.

        Each returned string is exactly *width* characters wide (padded with
        spaces).  The caller blits them onto the screen starting at row 0.

        Box layout::

            ┌─ title ─────────────────────────────────┐
            │  owa-mail                               │
            │  Settings / Help / ...                  │
            │                                         │
            │  > Resume                               │
            │    Settings                             │
            │    Help                                 │
            │    Quit                                 │
            │                                         │
            │  ↑/↓ navigate · enter select · esc back │
            └─────────────────────────────────────────┘

        The box is centered horizontally and vertically within *width* × *height*.
        Lines that do not fit within *height* are silently dropped (the caller
        can scroll or just live with fewer lines – the menu is intentionally
        compact).
        """
        # Build content lines (no padding yet)
        content = _build_content(self._screen, self._cursor, settings)

        # Box width: widest content line + 4 (2 side margins each side)
        inner_w = max((len(ln) for ln in content), default=0)
        box_w = inner_w + 4  # "  content  "
        box_w = max(box_w, 30)  # minimum sensible width
        box_w = min(box_w, width - 2)  # must fit in terminal (leave 1-col margin each side)
        box_w = max(box_w, 4)  # absolute minimum

        inner_w = box_w - 4

        # Build box lines
        top_border = "┌" + "─" * (box_w - 2) + "┐"
        bot_border = "└" + "─" * (box_w - 2) + "┘"
        box_lines: list[str] = [top_border]
        for ln in content:
            # truncate / pad to inner_w
            ln_fitted = (ln[:inner_w]).ljust(inner_w)
            box_lines.append("│  " + ln_fitted + "│")
        box_lines.append(bot_border)

        box_h = len(box_lines)

        # Center the box within width × height
        left_pad = max(0, (width - box_w) // 2)
        top_pad = max(0, (height - box_h) // 2)

        output: list[str] = []

        # blank lines above box
        blank = " " * width
        for _ in range(top_pad):
            output.append(blank)
            if len(output) >= height:
                break

        # box lines
        for bl in box_lines:
            if len(output) >= height:
                break
            padded = (" " * left_pad + bl).ljust(width)[:width]
            output.append(padded)

        # blank lines below box (fill to height)
        while len(output) < height:
            output.append(blank)

        return output


# ---------------------------------------------------------------------------
# Internal render helpers
# ---------------------------------------------------------------------------

_TITLE_LINES = [
    "owa-mail",
    "─" * 16,
]

_FOOTER = "↑/↓ navigate · enter select · esc back"


def _build_content(screen: str, cursor: int, settings: Any) -> list[str]:
    """Build the inner content lines (no box borders, no padding)."""
    lines: list[str] = []

    # Title block
    lines.extend(_TITLE_LINES)
    lines.append("")

    if screen == "top":
        for i, (label, _) in enumerate(_TOP_ITEMS):
            prefix = "> " if i == cursor else "  "
            lines.append(f"{prefix}{label}")
    else:
        # Settings screen
        meta = _get_settings_meta()
        rows_with_back = []
        for m in meta:
            field = m["field"]
            value = getattr(settings, field, "")
            rows_with_back.append((f"{m['label']}: {value}", field))
        rows_with_back.append(("Reset to defaults", "reset"))
        rows_with_back.append(("Back", "back"))

        for i, (label, _) in enumerate(rows_with_back):
            prefix = "> " if i == cursor else "  "
            lines.append(f"{prefix}{label}")

    lines.append("")
    lines.append(_FOOTER)

    return lines
