"""Tests for owa_mail.tui_menu – pure overlay-menu state machine.

No curses, no network, no I/O.

Coverage checklist (per the U6 spec):
  * Navigation clamp / wrap
  * select() returns correct Action for each top-level item
  * select() returns correct Action for each settings item
  * Settings rows reflect the current Settings values in the render label
  * render() produces lines centered within width × height
  * render() includes the footer
  * render() lines fit within width
"""

from __future__ import annotations

from dataclasses import dataclass

from owa_mail.tui_menu import Menu, _settings_action

# ---------------------------------------------------------------------------
# Minimal Settings stand-in (matches the U5 spec's field names / defaults)
# ---------------------------------------------------------------------------


@dataclass
class _Settings:
    reading_pane: str = "right"
    split_ratio: int = 50
    sort_by: str = "date_desc"
    date_format: str = "iso8601"
    date_custom: str = ""


def _default_settings() -> _Settings:
    return _Settings()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _top_menu() -> Menu:
    return Menu(screen="top")


def _settings_menu() -> Menu:
    m = Menu(screen="top")
    m.open_settings()
    return m


# ---------------------------------------------------------------------------
# Top-level navigation
# ---------------------------------------------------------------------------


class TestTopNavigation:
    def test_initial_cursor_is_zero(self):
        m = _top_menu()
        assert m.cursor == 0

    def test_move_down_increments_cursor(self):
        m = _top_menu()
        m.move(1)
        assert m.cursor == 1

    def test_move_clamps_at_zero(self):
        m = _top_menu()
        m.move(-5)
        assert m.cursor == 0

    def test_move_clamps_at_last_item(self):
        m = _top_menu()
        # 4 top items (Resume, Settings, Help, Quit) → max index 3
        m.move(100)
        assert m.cursor == 3

    def test_move_multiple_steps(self):
        m = _top_menu()
        m.move(2)
        assert m.cursor == 2
        m.move(-1)
        assert m.cursor == 1

    def test_move_wrap_wraps_past_end(self):
        m = _top_menu()
        # 4 items; at 0, delta=-1 wraps to 3
        m.move_wrap(-1)
        assert m.cursor == 3

    def test_move_wrap_wraps_past_start(self):
        m = _top_menu()
        m.move(3)  # at last item (3)
        m.move_wrap(1)
        assert m.cursor == 0


# ---------------------------------------------------------------------------
# Settings-screen navigation
# ---------------------------------------------------------------------------


class TestSettingsNavigation:
    def test_cursor_reset_on_open_settings(self):
        m = _top_menu()
        m.move(2)
        m.open_settings()
        assert m.cursor == 0

    def test_move_clamps_at_settings_last_item(self):
        m = _settings_menu()
        # 5 setting fields + "Back" = 6 items → max index 5
        m.move(100)
        assert m.cursor == 5

    def test_back_resets_to_top(self):
        m = _settings_menu()
        m.back()
        assert m.screen == "top"
        assert m.cursor == 0

    def test_back_on_top_screen_stays_top(self):
        m = _top_menu()
        m.back()
        assert m.screen == "top"


# ---------------------------------------------------------------------------
# select() on the top screen
# ---------------------------------------------------------------------------


class TestTopSelect:
    def test_resume(self):
        m = _top_menu()
        m._cursor = 0
        assert m.select() == "resume"

    def test_open_settings(self):
        m = _top_menu()
        m._cursor = 1
        assert m.select() == "open_settings"

    def test_help(self):
        m = _top_menu()
        m._cursor = 2
        assert m.select() == "help"

    def test_quit(self):
        m = _top_menu()
        m._cursor = 3
        assert m.select() == "quit"

    def test_out_of_range_returns_none(self):
        m = _top_menu()
        m._cursor = 99
        assert m.select() == "none"


# ---------------------------------------------------------------------------
# select() on the settings screen
# ---------------------------------------------------------------------------


class TestSettingsSelect:
    def test_reading_pane_returns_cycle(self):
        m = _settings_menu()
        m._cursor = 0  # reading_pane
        assert m.select(_default_settings()) == "cycle:reading_pane"

    def test_split_ratio_returns_cycle(self):
        m = _settings_menu()
        m._cursor = 1
        assert m.select(_default_settings()) == "cycle:split_ratio"

    def test_sort_by_returns_cycle(self):
        m = _settings_menu()
        m._cursor = 2
        assert m.select(_default_settings()) == "cycle:sort_by"

    def test_date_format_iso8601_returns_cycle(self):
        m = _settings_menu()
        m._cursor = 3  # date_format; current value is "iso8601"
        assert m.select(_default_settings()) == "cycle:date_format"

    def test_date_format_custom_returns_edit_custom(self):
        m = _settings_menu()
        m._cursor = 3  # date_format
        s = _Settings(date_format="custom")
        assert m.select(s) == "edit_custom"

    def test_date_custom_always_returns_edit_custom(self):
        m = _settings_menu()
        m._cursor = 4  # date_custom
        assert m.select(_default_settings()) == "edit_custom"

    def test_back_row_returns_back(self):
        m = _settings_menu()
        m._cursor = 5  # "Back" (index after the 5 fields)
        assert m.select(_default_settings()) == "back"

    def test_select_without_settings_object_falls_back_to_cycle(self):
        m = _settings_menu()
        m._cursor = 0  # reading_pane
        # When no settings is passed, non-custom fields → cycle:<field>
        assert m.select(None) == "cycle:reading_pane"


# ---------------------------------------------------------------------------
# _settings_action helper
# ---------------------------------------------------------------------------


class TestSettingsAction:
    def test_normal_field_returns_cycle(self):
        s = _Settings()
        assert _settings_action("reading_pane", s) == "cycle:reading_pane"
        assert _settings_action("split_ratio", s) == "cycle:split_ratio"
        assert _settings_action("sort_by", s) == "cycle:sort_by"

    def test_date_format_non_custom_returns_cycle(self):
        s = _Settings(date_format="iso8601")
        assert _settings_action("date_format", s) == "cycle:date_format"

    def test_date_format_custom_returns_edit_custom(self):
        s = _Settings(date_format="custom")
        assert _settings_action("date_format", s) == "edit_custom"

    def test_date_custom_always_edit_custom(self):
        s = _Settings(date_custom="")
        assert _settings_action("date_custom", s) == "edit_custom"
        s2 = _Settings(date_custom="%Y/%m/%d")
        assert _settings_action("date_custom", s2) == "edit_custom"


# ---------------------------------------------------------------------------
# items_for_settings – display labels reflect current Settings values
# ---------------------------------------------------------------------------


class TestItemsForSettings:
    def test_rows_contain_current_values(self):
        m = _settings_menu()
        s = _Settings(reading_pane="bottom", split_ratio=40, sort_by="sender",
                      date_format="ddmm", date_custom="%d/%m")
        rows = m.items_for_settings(s)
        # Five setting rows + Back
        assert len(rows) == 6
        assert any("bottom" in r for r in rows), rows
        assert any("40" in r for r in rows), rows
        assert any("sender" in r for r in rows), rows
        assert any("ddmm" in r for r in rows), rows
        assert any("%d/%m" in r for r in rows), rows
        assert rows[-1] == "Back"

    def test_rows_show_label_and_value(self):
        m = _settings_menu()
        s = _default_settings()
        rows = m.items_for_settings(s)
        # Each row (except Back) should look like "Label: value"
        for row in rows[:-1]:
            assert ":" in row, f"Expected 'Label: value' format, got: {row!r}"

    def test_default_settings_reflected(self):
        m = _settings_menu()
        rows = m.items_for_settings(_default_settings())
        assert any("right" in r for r in rows)
        assert any("50" in r for r in rows)
        assert any("date_desc" in r for r in rows)
        assert any("iso8601" in r for r in rows)


# ---------------------------------------------------------------------------
# render() – geometry and content
# ---------------------------------------------------------------------------


class TestRender:
    def test_returns_correct_number_of_lines(self):
        m = _top_menu()
        lines = m.render(80, 24, _default_settings())
        assert len(lines) == 24

    def test_all_lines_fit_within_width(self):
        for w in (40, 80, 120):
            m = _top_menu()
            lines = m.render(w, 20, _default_settings())
            for i, ln in enumerate(lines):
                assert len(ln) <= w, (
                    f"width={w}: line {i} has length {len(ln)}: {ln!r}"
                )

    def test_footer_present(self):
        m = _top_menu()
        lines = m.render(80, 24, _default_settings())
        joined = "\n".join(lines)
        assert "↑/↓ navigate" in joined
        assert "enter select" in joined
        assert "esc back" in joined

    def test_title_present(self):
        m = _top_menu()
        lines = m.render(80, 24, _default_settings())
        joined = "\n".join(lines)
        assert "owa-mail" in joined

    def test_cursor_item_marked_with_arrow(self):
        m = _top_menu()
        m._cursor = 0
        lines = m.render(80, 24, _default_settings())
        joined = "\n".join(lines)
        assert "> Resume" in joined

    def test_settings_screen_shows_current_values(self):
        m = _settings_menu()
        s = _Settings(reading_pane="off")
        lines = m.render(80, 24, s)
        joined = "\n".join(lines)
        assert "off" in joined

    def test_render_narrow_terminal_does_not_crash(self):
        m = _top_menu()
        # Very narrow – should not raise; lines may be truncated but must not error.
        lines = m.render(20, 10, _default_settings())
        assert len(lines) == 10
        for ln in lines:
            assert len(ln) <= 20

    def test_render_tiny_terminal_does_not_crash(self):
        m = _top_menu()
        lines = m.render(10, 5, _default_settings())
        assert len(lines) == 5
        for ln in lines:
            assert len(ln) <= 10

    def test_box_is_horizontally_centered(self):
        m = _top_menu()
        lines = m.render(80, 30, _default_settings())
        # The box top/bottom border contains '┌' and '┘'.
        # Find a border line and check it's roughly centered (not flush-left).
        border_lines = [ln for ln in lines if "┌" in ln or "└" in ln]
        assert border_lines, "No box border found in render output"
        for bl in border_lines:
            # There should be some left-padding (not starting at column 0 on
            # a wide terminal).
            assert bl[0] == " ", (
                f"Box border should be padded from left on 80-col terminal; got: {bl!r}"
            )

    def test_settings_render_includes_back(self):
        m = _settings_menu()
        lines = m.render(80, 30, _default_settings())
        joined = "\n".join(lines)
        assert "Back" in joined

    def test_render_does_not_exceed_height(self):
        m = _top_menu()
        for h in (5, 10, 20, 40):
            lines = m.render(80, h, _default_settings())
            assert len(lines) == h, f"height={h}: got {len(lines)} lines"


# ---------------------------------------------------------------------------
# open_settings / back round-trip through render
# ---------------------------------------------------------------------------


class TestScreenTransitions:
    def test_open_settings_changes_screen(self):
        m = _top_menu()
        assert m.screen == "top"
        m.open_settings()
        assert m.screen == "settings"

    def test_back_from_settings_returns_to_top(self):
        m = _top_menu()
        m.open_settings()
        m.back()
        assert m.screen == "top"

    def test_select_open_settings_then_navigate(self):
        m = _top_menu()
        m._cursor = 1  # "Settings" → open_settings
        action = m.select()
        assert action == "open_settings"
        m.open_settings()
        assert m.screen == "settings"
        m._cursor = 5  # "Back"
        assert m.select(_default_settings()) == "back"
        m.back()
        assert m.screen == "top"
