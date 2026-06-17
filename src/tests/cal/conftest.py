"""Shared fixtures for the owa-cal test suite.

No network. No real tokens. No writes outside tmp_path.
"""
import curses

import pytest

# ---------------------------------------------------------------------------
# Minimal FakeScreen + terminal stub for TUI tests
# (copied from src/tests/core/tui_kit/conftest.py to keep this suite
# self-contained without importing across package boundaries)
# ---------------------------------------------------------------------------

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
        self.buffer: dict = {}

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


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect owa_cal.config.CONFIG_PATH to a path under tmp_path."""
    fake_path = tmp_path / 'owa-cal' / 'config'
    from owa_cal import config as config_mod
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', fake_path)
    return fake_path


@pytest.fixture
def tmp_profiles(tmp_path, monkeypatch):
    """Redirect owa_cal.profiles.PROFILES_PATH to a path under tmp_path
    so add/delete/load operations don't touch the user's real file."""
    fake_path = tmp_path / 'owa-cal' / 'profiles.json'
    from owa_cal import profiles as profiles_mod
    monkeypatch.setattr(profiles_mod, 'PROFILES_PATH', fake_path)
    return fake_path


@pytest.fixture
def stub_piggy_aliases(monkeypatch):
    """Pin the (aliases, default) tuple returned by the piggy lister
    so tests don't shell out to a real owa-piggy. Returns a setter."""
    from owa_cal import profiles as profiles_mod

    def _set(aliases, default=''):
        monkeypatch.setattr(
            profiles_mod, 'piggy_aliases',
            lambda: (set(aliases), default),
        )

    _set([], '')
    return _set


@pytest.fixture
def clean_env(monkeypatch):
    """Strip env vars that could leak owa-piggy or owa-cal state between tests."""
    for key in (
        'OWA_PROFILE', 'CAL_DEBUG', 'XDG_CONFIG_HOME',
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def force_tz(monkeypatch):
    """Force the process-local timezone for a test.

    POSIX only - sets the TZ env var and calls time.tzset() so
    datetime.astimezone() picks up the right rules for *that* moment
    in time (DST-aware). Returns a setter so a single test can switch
    timezones, e.g. `force_tz('Europe/Oslo')`.
    """
    import time as time_mod

    def _set(tz):
        monkeypatch.setenv('TZ', tz)
        if hasattr(time_mod, 'tzset'):
            time_mod.tzset()

    return _set
