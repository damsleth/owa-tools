"""Tests for owa-cal TUI session building, the respond confirm-flow, and the
browser action (Phase: owa-cal adapter).

Focus: the mutating respond path (confirm prompt + reuse of api_request) and
the curses-safe browser launch. The kit's generic nav is covered by
test_kit_app.py; these exercise the cal-specific callbacks/lifecycle.
"""
from __future__ import annotations

import contextlib

from owa_cal import tui
from owa_cal.tui_settings import DEFAULTS as _SETTINGS_DEFAULTS


def _event(**kw):
    base = {'id': 'evt-1', 'subject': 'Standup', 'webLink': 'https://outlook/evt-1'}
    base.update(kw)
    return base


def _state(events=None, config=None):
    spec, state = tui.build_session(config or {}, 'tok', 'https://example.com/api/v2.0')
    if events is not None:
        state.items = events
    return state


# ---------------------------------------------------------------------------
# render_detail must not raise on a narrow/just-resized pane (regression)
# ---------------------------------------------------------------------------

def test_render_detail_narrow_width_does_not_raise():
    event = _event(body='A long body line that would need wrapping ' * 5,
                   organizer='boss@x.com', attendees=['a@x.com', 'b@x.com'])
    for width in (1, 2, 3):
        lines = tui.render_detail(event, width)  # textwrap width-2 <= 0 used to ValueError
        assert isinstance(lines, list)


# ---------------------------------------------------------------------------
# on_drill must not silently trap focus (read as a hang)
# ---------------------------------------------------------------------------

def test_drill_focuses_detail_with_hint_when_pane_on():
    state = _state([_event()])              # default reading_pane='right'
    tui.on_drill(state, state.items[0])
    assert state.focus == 'detail'
    assert 'back' in state.status.lower()   # discoverable escape

def test_drill_with_pane_off_hints_instead_of_trapping():
    state = _state([_event()], config={'tui_reading_pane': 'off'})
    tui.on_drill(state, state.items[0])
    assert state.focus != 'detail'          # not trapped
    assert 'reading pane' in state.status.lower()


def _answer(monkeypatch, value):
    """Make the confirm prompt return *value* without driving real curses."""
    monkeypatch.setattr(tui._screen, 'prompt', lambda stdscr, text: value)


# ---------------------------------------------------------------------------
# build_session
# ---------------------------------------------------------------------------

def test_build_session_wires_state_and_spec():
    spec, state = tui.build_session({}, 'tok', 'base', debug=True, day_range='week')
    assert state.access_token == 'tok'
    assert state.api_base == 'base'
    assert state.debug is True
    assert state._pending_respond is None
    assert state.settings.day_range == 'week'        # caller override applied
    assert spec.render_row is tui.render_row
    # respond keys stash a sentinel rather than acting (no stdscr in actions)
    spec.actions[tui._KEY_ACCEPT](state)
    assert state._pending_respond == 'accept'


def test_build_session_ignores_unknown_day_range():
    _, state = tui.build_session({}, 'tok', 'base', day_range='decade')
    assert state.settings.day_range == _SETTINGS_DEFAULTS.day_range


# ---------------------------------------------------------------------------
# _do_respond — the mutating confirm flow
# ---------------------------------------------------------------------------

def test_respond_confirmed_calls_api(monkeypatch):
    calls = {}

    def fake_api(method, api_base, endpoint, token, *, body=None, debug=False):
        calls.update(method=method, endpoint=endpoint, body=body)
        return {'ok': True}
    monkeypatch.setattr(tui.api_mod, 'api_request', fake_api)
    _answer(monkeypatch, 'y')
    state = _state([_event()])
    tui._do_respond(object(), state, 'accept')
    assert calls['method'] == 'POST'
    assert calls['endpoint'].endswith('/accept')
    assert state.status.startswith('accepted')
    assert state.dirty is True


def test_respond_cancelled_does_not_call_api(monkeypatch):
    def boom(*a, **k):
        raise AssertionError('must not send on a declined confirm')
    monkeypatch.setattr(tui.api_mod, 'api_request', boom)
    _answer(monkeypatch, 'n')
    state = _state([_event()])
    tui._do_respond(object(), state, 'accept')
    assert state.status == 'cancelled'


def test_respond_no_event_selected():
    state = _state([])
    tui._do_respond(object(), state, 'accept')
    assert state.status == 'no event selected'


def test_respond_prompt_error_is_caught(monkeypatch):
    def fake_prompt(stdscr, text):
        raise RuntimeError('tiny terminal')
    monkeypatch.setattr(tui._screen, 'prompt', fake_prompt)
    state = _state([_event()])
    tui._do_respond(object(), state, 'accept')
    assert state.status == 'prompt error'


def test_respond_api_failure_reported(monkeypatch):
    def fake_api(*a, **k):
        return None
    monkeypatch.setattr(tui.api_mod, 'api_request', fake_api)
    _answer(monkeypatch, 'y')
    state = _state([_event()])
    tui._do_respond(object(), state, 'decline')
    assert state.status == 'respond failed'


# ---------------------------------------------------------------------------
# _do_open_browser — curses-safe launch
# ---------------------------------------------------------------------------

def test_open_browser_with_link(monkeypatch):
    opened = {}
    monkeypatch.setattr(tui._screen, 'silence_os_fds', contextlib.nullcontext)
    monkeypatch.setattr(tui.webbrowser, 'open', lambda url: opened.setdefault('url', url))
    state = _state([_event()])
    tui._do_open_browser(state)
    assert opened['url'] == 'https://outlook/evt-1'
    assert state.status == 'opened in browser'


def test_open_browser_no_link():
    state = _state([_event(webLink='')])
    tui._do_open_browser(state)
    assert state.status == 'no web link for this event'


def test_open_browser_no_event():
    state = _state([])
    tui._do_open_browser(state)
    assert state.status == 'no event selected'
