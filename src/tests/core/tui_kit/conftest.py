"""Shared fixtures for tui_kit tests: a fake curses screen + terminal stub.

Lets the curses-bound kit (screen.py, app.py) be exercised with no real
terminal. Scoped to this directory so the curses monkeypatching never leaks
into other core tests.
"""
from __future__ import annotations

import curses

import pytest


class FakeScreen:
    """A minimal stand-in for a curses window.

    Records every ``addstr`` so tests can assert on rendered text, replays a
    scripted list of key codes from ``getch`` (falling back to ``q`` so any
    loop terminates), and returns scripted bytes from ``getstr``.
    """

    def __init__(self, h=24, w=80, keys=None, inputs=None):
        self._h = h
        self._w = w
        self._keys = list(keys or [])
        self._inputs = list(inputs or [])
        self.buffer: dict[tuple[int, int], str] = {}

    # geometry
    def getmaxyx(self):
        return (self._h, self._w)

    # input
    def getch(self):
        if self._keys:
            return self._keys.pop(0)
        return ord('q')  # guarantee any event loop terminates

    def getstr(self, *args):
        return self._inputs.pop(0) if self._inputs else b''

    # output
    def addstr(self, y, x, text, attr=0):
        self.buffer[(y, x)] = text

    def erase(self):
        self.buffer.clear()

    def clear(self):
        self.buffer.clear()

    def refresh(self):
        pass

    def keypad(self, flag):
        pass

    def bkgd(self, ch, attr=0):
        pass

    # helpers
    def text(self):
        return "\n".join(v for _, v in sorted(self.buffer.items()))


@pytest.fixture
def fake_screen():
    return FakeScreen


@pytest.fixture(autouse=True)
def _no_terminal(monkeypatch):
    """Neutralise curses calls that need a real terminal."""
    for name in (
        'curs_set', 'echo', 'noecho', 'use_default_colors',
        'init_pair', 'resizeterm', 'color_pair',
    ):
        monkeypatch.setattr(curses, name, lambda *a, **k: 0, raising=False)
