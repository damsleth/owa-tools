"""Loop + draw coverage for owa_core.tui_kit.app via a fake curses screen.

Drives ``app._loop`` directly (not ``run``, which wraps curses) to exercise
the frozen callback contract: fetch/render/drill/back/search/refresh/menu/
detail-pane/resize/quit.
"""
from __future__ import annotations

import curses

from owa_core.tui_kit import app
from owa_core.tui_kit.menu import Menu

MENU_TITLE = ["demo", "----"]
MENU_TOP = [("Resume", "resume"), ("Settings", "open_settings"), ("Quit", "quit")]
MENU_FIELDS = [("pane", "Reading pane")]


class PaneRight:
    reading_pane = "right"
    split_ratio = 50


def make_spec(detail_lines=None, **overrides):
    calls = {"fetched": 0, "drilled": [], "searched": [], "refreshed": 0,
             "menu": [], "action": 0, "back": 0}

    def fetch(state):
        calls["fetched"] += 1
        if not state.items and not overrides.get("leave_empty"):
            state.items = ["a", "b", "c"]

    spec = app.BrowserSpec(
        render_row=lambda it, w: f"row:{it}",
        render_detail=lambda it, w: (detail_lines or [f"detail:{it}"]),
        fetch_items=fetch,
        on_search=lambda st, q: calls["searched"].append(q),
        on_drill=lambda st, it: calls["drilled"].append(it),
        on_back=lambda st: (calls.update(back=calls["back"] + 1),
                            overrides.get("back_ok", True))[1],
        on_refresh=lambda st: calls.update(refreshed=calls["refreshed"] + 1),
        on_menu_action=lambda st, a: (calls["menu"].append(a), False)[1],
        actions={ord("x"): lambda st: calls.update(action=calls["action"] + 1)},
    )
    return spec, calls


def run(fake_screen, keys, *, settings=None, menu=None, inputs=None,
        spec_kwargs=None, **spec_overrides):
    spec, calls = make_spec(**(spec_kwargs or {}), **spec_overrides)
    state = app.BrowserState(settings=settings, menu=menu, title="T")
    screen = fake_screen(keys=keys, inputs=inputs)
    app._loop(screen, state, spec)
    return state, calls, screen


class TestLoopResilience:
    """A render/handler bug must not escape the loop or freeze the UI."""

    def test_action_exception_does_not_kill_loop(self, fake_screen):
        def boom(st):
            raise RuntimeError("kaboom")
        spec = app.BrowserSpec(
            render_row=lambda it, w: f"row:{it}",
            render_detail=lambda it, w: ["d"],
            fetch_items=lambda st: setattr(st, "items", ["a"]),
            actions={ord("x"): boom},
        )
        state = app.BrowserState(title="T")
        screen = fake_screen(keys=[ord("x")])  # then falls back to 'q'
        app._loop(screen, state, spec)          # must not propagate
        assert state.running is False           # 'q' still quit it cleanly

    def test_draw_exception_does_not_spin_or_kill(self, fake_screen):
        def bad_row(it, w):
            raise ValueError("bad render")
        spec = app.BrowserSpec(
            render_row=bad_row,
            render_detail=lambda it, w: ["d"],
            fetch_items=lambda st: setattr(st, "items", ["a"]),
        )
        state = app.BrowserState(title="T")
        screen = fake_screen(keys=[ord("q")])   # getch is still reached after a bad frame
        app._loop(screen, state, spec)           # must not raise or spin
        assert state.running is False


class TestFetchAndRender:
    def test_first_iteration_fetches(self, fake_screen):
        state, calls, _ = run(fake_screen, [ord("q")])
        assert calls["fetched"] == 1
        assert state.items == ["a", "b", "c"]

    def test_rows_rendered(self, fake_screen):
        _, _, screen = run(fake_screen, [ord("q")])
        assert "row:a" in screen.text()

    def test_empty_shows_empty_text(self, fake_screen):
        _, calls, screen = run(fake_screen, [ord("q")], leave_empty=True)
        assert "(empty)" in screen.text()


class TestNavigation:
    def test_j_moves_down(self, fake_screen):
        state, _, _ = run(fake_screen, [ord("j"), ord("q")])
        assert state.selected == 1

    def test_k_moves_up(self, fake_screen):
        state, _, _ = run(fake_screen, [ord("j"), ord("j"), ord("k"), ord("q")])
        assert state.selected == 1

    def test_G_jumps_to_bottom(self, fake_screen):
        state, _, _ = run(fake_screen, [ord("G"), ord("q")])
        assert state.selected == 2

    def test_g_jumps_to_top(self, fake_screen):
        state, _, _ = run(fake_screen, [ord("G"), ord("g"), ord("q")])
        assert state.selected == 0

    def test_arrow_down(self, fake_screen):
        state, _, _ = run(fake_screen, [curses.KEY_DOWN, ord("q")])
        assert state.selected == 1


class TestDrillBackSearchRefresh:
    def test_enter_drills(self, fake_screen):
        _, calls, _ = run(fake_screen, [10, ord("q")])
        assert calls["drilled"] == ["a"]

    def test_drill_on_empty_is_noop(self, fake_screen):
        _, calls, _ = run(fake_screen, [10, ord("q")], leave_empty=True)
        assert calls["drilled"] == []

    def test_back_pops(self, fake_screen):
        _, calls, _ = run(fake_screen, [ord("h"), ord("q")])
        assert calls["back"] == 1

    def test_back_false_keeps_view(self, fake_screen):
        state, calls, _ = run(fake_screen, [ord("h"), ord("q")], back_ok=False)
        assert calls["back"] == 1  # called, returned False -> no-op

    def test_search_prompts_and_calls(self, fake_screen):
        _, calls, _ = run(fake_screen, [ord("/"), ord("q")], inputs=[b"budget"])
        assert calls["searched"] == ["budget"]

    def test_refresh(self, fake_screen):
        _, calls, _ = run(fake_screen, [ord("r"), ord("q")])
        assert calls["refreshed"] == 1

    def test_custom_action(self, fake_screen):
        _, calls, _ = run(fake_screen, [ord("x"), ord("q")])
        assert calls["action"] == 1

    def test_unknown_key_is_noop(self, fake_screen):
        state, _, _ = run(fake_screen, [ord("z"), ord("q")])
        assert state.selected == 0


class TestDetailPane:
    def test_right_arrow_focuses_detail(self, fake_screen):
        state, _, _ = run(fake_screen, [curses.KEY_RIGHT, ord("q")],
                          settings=PaneRight())
        assert state.focus == "detail"

    def test_detail_scrolls(self, fake_screen):
        long = [f"L{i}" for i in range(50)]
        state, _, _ = run(fake_screen, [curses.KEY_RIGHT, ord("j"), ord("q")],
                          settings=PaneRight(), spec_kwargs={"detail_lines": long})
        assert state.detail_top == 1

    def test_back_returns_to_list(self, fake_screen):
        state, _, _ = run(fake_screen,
                          [curses.KEY_RIGHT, ord("h"), ord("q")],
                          settings=PaneRight())
        assert state.focus == "list"

    def test_detail_rendered(self, fake_screen):
        _, _, screen = run(fake_screen, [ord("q")], settings=PaneRight())
        assert "detail:a" in screen.text()


class TestMenu:
    def _menu(self):
        return Menu(MENU_TITLE, MENU_TOP, MENU_FIELDS)

    def test_esc_opens_menu(self, fake_screen):
        # esc opens, esc closes, q quits
        state, _, _ = run(fake_screen, [27, 27, ord("q")], menu=self._menu())
        assert state.menu_open is False

    def test_menu_resume_closes(self, fake_screen):
        state, _, _ = run(fake_screen, [27, 10, ord("q")], menu=self._menu())
        assert state.menu_open is False

    def test_menu_quit(self, fake_screen):
        # esc, down->Settings, down->Quit, enter
        state, _, _ = run(fake_screen, [27, ord("j"), ord("j"), 10],
                          menu=self._menu())
        assert state.running is False

    def test_menu_navigates_to_settings_and_acts(self, fake_screen):
        # esc, down->Settings, enter->open_settings, enter->cycle:pane,
        # esc->back, esc->close, q
        keys = [27, ord("j"), 10, 10, 27, 27, ord("q")]
        _, calls, _ = run(fake_screen, keys, menu=self._menu(),
                          settings=PaneRight())
        assert "cycle:pane" in calls["menu"]

    def test_menu_nav_up(self, fake_screen):
        # esc, up (clamps at 0), enter -> resume, q
        state, _, _ = run(fake_screen, [27, ord("k"), 10, ord("q")],
                          menu=self._menu())
        assert state.menu_open is False


class TestResizeAndQuit:
    def test_resize_no_crash(self, fake_screen):
        state, _, _ = run(fake_screen, [curses.KEY_RESIZE, ord("q")])
        assert state.running is False

    def test_q_quits(self, fake_screen):
        state, _, _ = run(fake_screen, [ord("q")])
        assert state.running is False
