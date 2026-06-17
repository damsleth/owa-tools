"""Generic esc-overlay menu state machine for owa-* TUIs.

Pure: no curses, no I/O. A tool supplies its title lines, top-level items
and the list of settings fields; navigation, selection and the centered
box render are shared. Tools needing a per-field select quirk (e.g.
owa-mail's ``date_custom`` → ``edit_custom``) subclass and override
:meth:`Menu._settings_action`.

Action strings returned by :meth:`Menu.select`:
    top screen      -> whatever action each top item declares
                       (e.g. ``resume`` / ``open_settings`` / ``help`` / ``quit``)
    settings screen -> ``cycle:<field>`` (default), ``reset_settings``,
                       ``back``, or a subclass-defined action.
    out of range    -> ``none``
"""
from __future__ import annotations

from typing import Any

DEFAULT_FOOTER = "↑/↓ navigate · enter select · esc back"


class Menu:
    """Pure overlay-menu state machine.

    Parameters
    ----------
    title_lines     : header lines drawn at the top of the box.
    top_items       : ``[(label, action), …]`` for the top screen.
    settings_fields : ``[(field, label), …]`` rendered (with current values)
                      on the settings screen, followed by Reset / Back rows.
    footer          : the hint line at the bottom of the box.
    screen          : starting screen — ``"top"`` or ``"settings"``.
    """

    def __init__(self, title_lines, top_items, settings_fields, *,
                 footer=DEFAULT_FOOTER, screen="top"):
        self._title_lines = list(title_lines)
        self._top_items = list(top_items)
        self._settings_fields = list(settings_fields)
        self._footer = footer
        self._screen = screen
        self._cursor = 0

    # ------------------------------------------------------------------ props

    @property
    def screen(self) -> str:
        return self._screen

    @property
    def cursor(self) -> int:
        return self._cursor

    # ------------------------------------------------------------------ items

    def _items(self) -> list[tuple[str, str]]:
        """Return ``(display_label, raw_action)`` for the current screen.

        On the settings screen the raw action is the field name; the final
        action is resolved by :meth:`select` after inspecting the settings.
        """
        if self._screen == "top":
            return list(self._top_items)
        return ([(label, field) for field, label in self._settings_fields]
                + [("Reset to defaults", "reset"), ("Back", "back")])

    def items_for_settings(self, settings: Any) -> list[str]:
        """Display labels for the settings screen (includes current values)."""
        rows = [f"{label}: {getattr(settings, field, '')}"
                for field, label in self._settings_fields]
        rows.append("Reset to defaults")
        rows.append("Back")
        return rows

    # -------------------------------------------------------------------- nav

    def move(self, delta: int) -> None:
        """Move the cursor by *delta* rows, clamping to ``[0, len-1]``."""
        n = len(self._items())
        if n == 0:
            self._cursor = 0
            return
        self._cursor = max(0, min(n - 1, self._cursor + delta))

    def move_wrap(self, delta: int) -> None:
        """Move the cursor by *delta* rows, wrapping around."""
        n = len(self._items())
        if n == 0:
            self._cursor = 0
            return
        self._cursor = (self._cursor + delta) % n

    # ---------------------------------------------------------------- actions

    def select(self, settings: Any | None = None) -> str:
        """Return the action string for the currently highlighted item."""
        items = self._items()
        if not items or self._cursor >= len(items):
            return "none"

        if self._screen == "top":
            _, action = items[self._cursor]
            return action

        # settings screen
        _, field = items[self._cursor]
        if field == "back":
            return "back"
        if field == "reset":
            return "reset_settings"
        if settings is None:
            return f"cycle:{field}"
        return self._settings_action(field, settings)

    def _settings_action(self, field: str, settings: Any) -> str:
        """Resolve a settings-row action. Default: cycle the field.

        Subclasses override to special-case fields (e.g. free-text editors).
        """
        return f"cycle:{field}"

    def back(self) -> None:
        """Navigate one level back (settings → top; top stays at top)."""
        if self._screen == "settings":
            self._screen = "top"
            self._cursor = 0

    def open_settings(self) -> None:
        """Navigate to the settings screen."""
        self._screen = "settings"
        self._cursor = 0

    def reset(self) -> None:
        """Return to the top screen with the cursor at the first item."""
        self._screen = "top"
        self._cursor = 0

    # ----------------------------------------------------------------- render

    def render(self, width: int, height: int, settings: Any) -> list[str]:
        """Render the overlay as a list of exactly *width*-wide strings.

        The box is centered horizontally and vertically within
        *width* × *height*; lines that do not fit in *height* are dropped.
        The returned list is always exactly *height* lines long.
        """
        content = self._build_content(settings)

        inner_w = max((len(ln) for ln in content), default=0)
        box_w = inner_w + 4  # "  content  "
        box_w = max(box_w, 30)            # minimum sensible width
        box_w = min(box_w, width - 2)     # leave a 1-col margin each side
        box_w = max(box_w, 4)             # absolute minimum

        inner_w = box_w - 4

        top_border = "┌" + "─" * (box_w - 2) + "┐"
        bot_border = "└" + "─" * (box_w - 2) + "┘"
        box_lines = [top_border]
        for ln in content:
            ln_fitted = (ln[:inner_w]).ljust(inner_w)
            box_lines.append("│  " + ln_fitted + "│")
        box_lines.append(bot_border)

        box_h = len(box_lines)

        left_pad = max(0, (width - box_w) // 2)
        top_pad = max(0, (height - box_h) // 2)

        output: list[str] = []
        blank = " " * width
        for _ in range(top_pad):
            output.append(blank)
            if len(output) >= height:
                break

        for bl in box_lines:
            if len(output) >= height:
                break
            output.append((" " * left_pad + bl).ljust(width)[:width])

        while len(output) < height:
            output.append(blank)

        return output

    def _build_content(self, settings: Any) -> list[str]:
        """Inner content lines (no box borders, no padding)."""
        lines: list[str] = list(self._title_lines)
        lines.append("")

        if self._screen == "top":
            rows = [label for label, _ in self._top_items]
        else:
            rows = self.items_for_settings(settings)

        for i, label in enumerate(rows):
            prefix = "> " if i == self._cursor else "  "
            lines.append(f"{prefix}{label}")

        lines.append("")
        lines.append(self._footer)
        return lines
