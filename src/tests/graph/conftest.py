"""Response-payload fixtures for the owa-graph TUI nav-engine tests.

These mirror the distinct shapes the explorer must handle across audiences:
an OData collection, an ARM collection (bare `nextLink` + absolute-id items),
an opaque-internal JSON object with no top-level `value`, a Tier-D scalar, a
genuinely non-JSON body, and a devops response that carries its continuation
cursor in a response *header*.
"""
from __future__ import annotations

import json

import pytest

from owa_graph import tui_nav


def _result(payload, *, status=200, headers=None):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return tui_nav.FetchResult(status=status, headers=dict(headers or {}), body=body)


@pytest.fixture
def graph_collection():
    """Graph `value` page with an `@odata.nextLink` and GUID-id items."""
    return {
        '@odata.context': 'https://graph.microsoft.com/v1.0/$metadata#users',
        '@odata.nextLink': 'https://graph.microsoft.com/v1.0/users?$skiptoken=abc',
        'value': [
            {'id': '11111111-1111-1111-1111-111111111111', 'displayName': 'Ada'},
            {'id': '22222222-2222-2222-2222-222222222222', 'displayName': 'Babbage'},
        ],
    }


@pytest.fixture
def arm_subscriptions():
    """ARM list with a *bare* top-level `nextLink` and absolute-path ids."""
    return {
        'nextLink': 'https://management.azure.com/subscriptions?$skip=2',
        'value': [
            {'id': '/subscriptions/aaaa', 'displayName': 'Prod'},
            {'id': '/subscriptions/bbbb', 'displayName': 'Dev'},
        ],
    }


@pytest.fixture
def teams_opaque():
    """Valid JSON object with no top-level `value` (an opaque internal API)."""
    return {'properties': {'presence': 'Available'}, 'etag': 'W/"x"'}


@pytest.fixture
def tier_d_scalar():
    """A bare JSON scalar (Tier-D data-plane response)."""
    return b'"OK"'


@pytest.fixture
def non_json_body():
    """A genuinely non-JSON body — the only path to `kind='opaque'`."""
    return b'\x89PNG\r\n\x1a\n not json at all'


@pytest.fixture
def devops_continuation():
    """A devops page whose cursor is in `X-MS-ContinuationToken` (note the
    server's mixed casing — a plain `.get` would miss it)."""
    payload = {'value': [{'id': 'proj-1', 'name': 'Alpha'}], 'count': 1}
    headers = {'X-MS-ContinuationToken': 'CT-TOKEN-42', 'Content-Type': 'application/json'}
    return payload, headers


@pytest.fixture
def make_result():
    """Factory: build a FetchResult from a payload (dict→JSON, bytes verbatim)."""
    return _result


# ---------------------------------------------------------------------------
# Fake curses screen + terminal stub for TUI loop tests (Phase 2)
# Copied from src/tests/core/tui_kit/conftest.py so graph tests are
# self-contained and don't share scope with core tests.
# ---------------------------------------------------------------------------

import curses  # noqa: E402 — import after existing stdlib imports


class FakeScreen:
    """A minimal stand-in for a curses window.

    Records every ``addstr`` call so tests can assert on rendered text,
    replays a scripted list of key codes from ``getch`` (falling back to
    ``q`` so any loop terminates), and returns scripted bytes from
    ``getstr``.
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
        return '\n'.join(v for _, v in sorted(self.buffer.items()))


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
