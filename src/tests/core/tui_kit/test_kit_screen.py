"""Tests for owa_core.tui_kit.screen — safe drawing + line input."""
from __future__ import annotations

import curses
import os

import pytest

from owa_core.tui_kit import screen as scr


class TestSilenceOsFds:
    def test_restores_fd2_and_returns(self):
        before = os.fstat(2)
        with scr.silence_os_fds():
            # writing inside goes to /dev/null, never the terminal, no error
            os.write(2, b'into the void')
        after = os.fstat(2)
        # fd 2 points back at the original target after the block
        assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)

    def test_propagates_exceptions_but_still_restores(self):
        before = os.fstat(2)
        with pytest.raises(ValueError):
            with scr.silence_os_fds():
                raise ValueError('boom')
        after = os.fstat(2)
        assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)


class TestSafeAddstr:
    def test_writes_within_bounds(self, fake_screen):
        s = fake_screen(h=5, w=20)
        scr.safe_addstr(s, 1, 0, "hello")
        assert s.buffer[(1, 0)] == "hello"

    def test_out_of_range_y_is_noop(self, fake_screen):
        s = fake_screen(h=5, w=20)
        scr.safe_addstr(s, 99, 0, "x")
        assert s.buffer == {}

    def test_negative_y_is_noop(self, fake_screen):
        s = fake_screen(h=5, w=20)
        scr.safe_addstr(s, -1, 0, "x")
        assert s.buffer == {}

    def test_x_past_width_is_noop(self, fake_screen):
        s = fake_screen(h=5, w=10)
        scr.safe_addstr(s, 0, 20, "x")
        assert s.buffer == {}

    def test_clips_to_width(self, fake_screen):
        s = fake_screen(h=5, w=10)
        scr.safe_addstr(s, 0, 0, "0123456789abcdef")
        assert len(s.buffer[(0, 0)]) <= 9

    def test_swallows_curses_error(self, fake_screen, monkeypatch):
        s = fake_screen(h=5, w=10)

        def boom(*a, **k):
            raise curses.error("nope")

        monkeypatch.setattr(s, "addstr", boom)
        scr.safe_addstr(s, 0, 0, "x")  # must not raise


class TestPrompt:
    def test_returns_decoded_input(self, fake_screen):
        s = fake_screen(h=5, w=40, inputs=[b"budget"])
        assert scr.prompt(s, "search: ") == "budget"

    def test_empty_input(self, fake_screen):
        s = fake_screen(h=5, w=40)
        assert scr.prompt(s, "q: ") == ""

    def test_none_when_getstr_none(self, fake_screen, monkeypatch):
        s = fake_screen(h=5, w=40)
        monkeypatch.setattr(s, "getstr", lambda *a: None)
        assert scr.prompt(s, "q: ") is None


class TestInitColors:
    def test_runs_without_terminal(self, fake_screen):
        scr.init_colors(fake_screen())  # neutralised curses; must not raise
