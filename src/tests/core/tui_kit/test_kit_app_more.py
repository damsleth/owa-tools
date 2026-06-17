"""Edge-path coverage for owa_core.tui_kit.app (scroll, panes, page nav, menu)."""
from __future__ import annotations

import curses

from owa_core.tui_kit import app
from owa_core.tui_kit.menu import Menu


class PaneBottom:
    reading_pane = "bottom"
    split_ratio = 50


class PaneRight:
    reading_pane = "right"
    split_ratio = 50


def _spec(detail_lines=None, on_refresh=None):
    spec = app.BrowserSpec(
        render_row=lambda it, w: f"row:{it}",
        render_detail=lambda it, w: (detail_lines or [f"detail:{it}"]),
        fetch_items=lambda st: None,  # caller pre-populates items
        on_refresh=on_refresh,
    )
    return spec


def _drive(fake_screen, items, keys, *, settings=None, spec=None,
           selected=0, focus="list", inputs=None):
    spec = spec or _spec()
    state = app.BrowserState(settings=settings, title="T", items=items)
    state.selected = selected
    state.focus = focus
    state.dirty = False  # items already supplied
    screen = fake_screen(keys=keys, inputs=inputs)
    app._loop(screen, state, spec)
    return state, screen


def _items(n):
    return [f"i{k}" for k in range(n)]


class TestScroll:
    def test_negative_selected_clamps_to_zero(self, fake_screen):
        state, _ = _drive(fake_screen, _items(5), [ord("q")], selected=-3)
        assert state.selected == 0

    def test_scroll_down_advances_top(self, fake_screen):
        state, _ = _drive(fake_screen, _items(60), [ord("G"), ord("q")])
        assert state.top > 0
        assert state.selected == 59

    def test_scroll_back_to_top(self, fake_screen):
        state, _ = _drive(fake_screen, _items(60),
                          [ord("G"), ord("g"), ord("q")])
        assert state.top == 0 and state.selected == 0

    def test_move_on_empty_is_noop(self, fake_screen):
        state, _ = _drive(fake_screen, [], [ord("j"), ord("q")])
        assert state.selected == 0


class TestPageNav:
    def test_half_page_down(self, fake_screen):
        state, _ = _drive(fake_screen, _items(60), [ord("d"), ord("q")])
        assert state.selected == (24 - 2) // 2  # half of body height

    def test_half_page_up(self, fake_screen):
        state, _ = _drive(fake_screen, _items(60),
                          [ord("G"), ord("u"), ord("q")])
        assert state.selected < 59

    def test_page_down(self, fake_screen):
        state, _ = _drive(fake_screen, _items(60),
                          [curses.KEY_NPAGE, ord("q")])
        assert state.selected == 24 - 2

    def test_page_up(self, fake_screen):
        state, _ = _drive(fake_screen, _items(60),
                          [ord("G"), curses.KEY_PPAGE, ord("q")])
        assert state.selected < 59


class TestBottomPane:
    def test_divider_and_detail_drawn(self, fake_screen):
        _, screen = _drive(fake_screen, _items(3), [ord("q")],
                           settings=PaneBottom())
        text = screen.text()
        assert "─" in text
        assert "detail:i0" in text


class TestDetailScroll:
    def test_half_page_down_up(self, fake_screen):
        long = [f"L{k}" for k in range(80)]
        spec = _spec(detail_lines=long)
        state, _ = _drive(fake_screen, _items(3),
                          [ord("d"), ord("u"), ord("q")],
                          settings=PaneRight(), focus="detail", spec=spec)
        assert state.detail_top == 0  # down a half then up a half

    def test_single_line_up_clamps(self, fake_screen):
        long = [f"L{k}" for k in range(80)]
        spec = _spec(detail_lines=long)
        state, _ = _drive(fake_screen, _items(3), [ord("k"), ord("q")],
                          settings=PaneRight(), focus="detail", spec=spec)
        assert state.detail_top == 0


class TestStatusHeader:
    def test_status_shown_in_header(self, fake_screen):
        def refresh(st):
            st.status = "minting…"

        spec = _spec(on_refresh=refresh)
        _, screen = _drive(fake_screen, _items(3), [ord("r"), ord("q")],
                           spec=spec)
        assert "minting…" in screen.text()


class TestMenuEdges:
    def _menu(self):
        return Menu(["t"], [("Resume", "resume"), ("Settings", "open_settings"),
                            ("Quit", "quit")], [("pane", "Pane")])

    def test_select_back_row_pops_to_top(self, fake_screen):
        # esc, j->Settings, enter->open_settings, j,j->Back row, enter->back,
        # esc->close, q
        keys = [27, ord("j"), 10, ord("j"), ord("j"), 10, 27, ord("q")]
        state = app.BrowserState(settings=PaneRight(), menu=self._menu(),
                                 title="T", items=_items(3))
        state.dirty = False
        app._loop(fake_screen(keys=keys), state, _spec())
        assert state.menu.screen == "top"
        assert state.menu_open is False

    def test_quit_from_menu(self, fake_screen):
        keys = [27, ord("j"), ord("j"), 10]
        state = app.BrowserState(settings=PaneRight(), menu=self._menu(),
                                 title="T", items=_items(3))
        state.dirty = False
        app._loop(fake_screen(keys=keys), state, _spec())
        assert state.running is False

    def test_esc_with_no_menu_is_noop(self, fake_screen):
        # menu is None -> esc falls through to list handler -> no-op, then q
        state, _ = _drive(fake_screen, _items(3), [27, ord("q")])
        assert state.running is False
