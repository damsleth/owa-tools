"""Tests for owa_core.tui_kit.menu — generic overlay-menu state machine."""
from __future__ import annotations

from dataclasses import dataclass

from owa_core.tui_kit.menu import Menu

TITLE = ["demo", "----"]
TOP = [("Resume", "resume"), ("Settings", "open_settings"), ("Quit", "quit")]
FIELDS = [("pane", "Reading pane"), ("ratio", "Split ratio")]


@dataclass
class S:
    pane: str = "right"
    ratio: int = 50


def _menu(screen="top"):
    return Menu(TITLE, TOP, FIELDS, screen=screen)


class TestNav:
    def test_move_clamps_top(self):
        m = _menu()
        m.move(100)
        assert m.cursor == 2  # 3 top items -> max index 2

    def test_move_clamps_low(self):
        m = _menu()
        m.move(-5)
        assert m.cursor == 0

    def test_move_wrap(self):
        m = _menu()
        m.move_wrap(-1)
        assert m.cursor == 2

    def test_settings_has_fields_plus_reset_back(self):
        m = _menu("settings")
        m.move(100)
        assert m.cursor == 3  # 2 fields + reset + back -> max index 3


class TestTopSelect:
    def test_resume(self):
        assert _menu().select() == "resume"

    def test_quit(self):
        m = _menu()
        m.move(2)
        assert m.select() == "quit"

    def test_out_of_range(self):
        m = _menu()
        m._cursor = 99
        assert m.select() == "none"


class TestSettingsSelect:
    def test_field_cycles_by_default(self):
        m = _menu("settings")
        assert m.select(S()) == "cycle:pane"

    def test_field_cycles_when_settings_none(self):
        m = _menu("settings")
        assert m.select(None) == "cycle:pane"

    def test_reset_row(self):
        m = _menu("settings")
        m._cursor = 2
        assert m.select(S()) == "reset_settings"

    def test_back_row(self):
        m = _menu("settings")
        m._cursor = 3
        assert m.select(S()) == "back"


class TestSubclassOverride:
    def test_custom_settings_action(self):
        class Custom(Menu):
            def _settings_action(self, field, settings):
                return f"edit:{field}"

        m = Custom(TITLE, TOP, FIELDS, screen="settings")
        assert m.select(S()) == "edit:pane"


class TestTransitions:
    def test_open_settings(self):
        m = _menu()
        m.open_settings()
        assert m.screen == "settings" and m.cursor == 0

    def test_back_from_settings(self):
        m = _menu("settings")
        m._cursor = 2
        m.back()
        assert m.screen == "top" and m.cursor == 0

    def test_back_on_top_is_noop(self):
        m = _menu()
        m.back()
        assert m.screen == "top"

    def test_reset(self):
        m = _menu("settings")
        m._cursor = 2
        m.reset()
        assert m.screen == "top" and m.cursor == 0


class TestRender:
    def test_exact_height(self):
        for h in (5, 10, 24, 40):
            assert len(_menu().render(80, h, S())) == h

    def test_all_lines_fit_width(self):
        for w in (40, 80, 120):
            for ln in _menu().render(w, 24, S()):
                assert len(ln) <= w

    def test_title_and_footer_present(self):
        joined = "\n".join(_menu().render(80, 24, S()))
        assert "demo" in joined
        assert "navigate" in joined

    def test_cursor_marked(self):
        joined = "\n".join(_menu().render(80, 24, S()))
        assert "> Resume" in joined

    def test_settings_shows_values(self):
        joined = "\n".join(_menu("settings").render(80, 24, S()))
        assert "Reading pane: right" in joined
        assert "Back" in joined

    def test_items_for_settings(self):
        rows = _menu("settings").items_for_settings(S())
        assert rows[0] == "Reading pane: right"
        assert rows[-1] == "Back"
        assert rows[-2] == "Reset to defaults"
