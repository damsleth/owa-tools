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


def _rich_event(**kw):
    base = {
        'subject': 'Hagefest', 'start': '2026-06-05T17:00:00',
        'end': '2026-06-05T23:30:00', 'location': 'Villa Grande',
        'showAs': 'Busy', 'categories': ['IGNORE'],
        'organizer': 'Boss', 'response': 'tentativelyAccepted',
        'body': 'HUSK PÅMELDINGSSKJEMA',
        'attendees': [
            {'name': 'Ada', 'address': 'ada@x.com', 'type': 'required', 'response': 'accepted'},
            {'name': 'Bo', 'address': 'bo@x.com', 'type': 'optional', 'response': 'declined'},
        ],
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# render_detail basic vs full
# ---------------------------------------------------------------------------

def test_render_detail_full_shows_attendees_organizer_body_response():
    text = '\n'.join(tui.render_detail(_rich_event(), 80, detail='full'))
    assert 'Organizer:Boss' in text
    assert 'Attendees (2):' in text
    assert 'Ada — accepted' in text
    assert 'Bo — declined (optional)' in text   # optional flagged, response mapped
    assert 'Response: tentative' in text         # own RSVP, label normalized
    assert 'PÅMELDINGSSKJEMA' in text            # body preview


def test_render_detail_basic_omits_rich_fields():
    text = '\n'.join(tui.render_detail(_rich_event(), 80, detail='basic'))
    # basic keeps the cheap fields...
    assert 'Hagefest' in text
    assert 'Villa Grande' in text
    assert 'Busy' in text
    assert 'IGNORE' in text
    # ...and drops the heavy ones
    assert 'Attendees' not in text
    assert 'Organizer' not in text
    assert 'PÅMELDINGSSKJEMA' not in text


def test_render_detail_no_longer_shows_truncated_id():
    text = '\n'.join(tui.render_detail(_rich_event(id='AAMkLONGID' * 5), 80))
    assert 'ID:' not in text


def test_render_detail_organizer_response_shown_for_organizer():
    text = '\n'.join(tui.render_detail(_rich_event(isOrganizer=True), 80, detail='full'))
    assert 'Response: organizer' in text


# ---------------------------------------------------------------------------
# render_detail must not raise on a narrow/just-resized pane (regression)
# ---------------------------------------------------------------------------

def test_render_detail_narrow_width_does_not_raise():
    event = _rich_event()
    for width in (1, 2, 3):
        for level in ('full', 'basic'):
            lines = tui.render_detail(event, width, detail=level)  # width-2<=0 used to ValueError
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


# ---------------------------------------------------------------------------
# build_session
# ---------------------------------------------------------------------------

def test_build_session_wires_state_and_spec():
    spec, state = tui.build_session({}, 'tok', 'base', debug=True, day_range='week')
    assert state.access_token == 'tok'
    assert state.api_base == 'base'
    assert state.debug is True
    assert state._respond_mode is False
    assert state.settings.day_range == 'week'        # caller override applied
    assert spec.render_row is tui.render_row
    # `y` arms respond mode; it does not send (the a/t/d second key does).
    assert tui._KEY_RESPOND in spec.actions
    assert tui._KEY_OPEN in spec.actions


def test_build_session_ignores_unknown_day_range():
    _, state = tui.build_session({}, 'tok', 'base', day_range='decade')
    assert state.settings.day_range == _SETTINGS_DEFAULTS.day_range


# ---------------------------------------------------------------------------
# respond chord: `y` arms, then a/t/d sends (no separate confirm prompt)
# ---------------------------------------------------------------------------

def test_enter_respond_mode_arms_when_event_selected():
    state = _state([_event()])
    tui._enter_respond_mode(state)
    assert state._respond_mode is True
    assert state.status.lower().startswith('respond:')


def test_enter_respond_mode_noop_without_event():
    state = _state([])
    tui._enter_respond_mode(state)
    assert state._respond_mode is False
    assert state.status == 'no event selected'


def test_respond_keys_map_to_actions():
    assert tui._RESPOND_KEYS == {ord('a'): 'accept', ord('t'): 'tentative', ord('d'): 'decline'}


def test_do_respond_sends_and_refetches(monkeypatch):
    calls = {}

    def fake_api(method, api_base, endpoint, token, *, body=None, debug=False):
        calls.update(method=method, endpoint=endpoint, body=body)
        return {'ok': True}
    monkeypatch.setattr(tui.api_mod, 'api_request', fake_api)
    state = _state([_event()])
    tui._do_respond(state, 'accept')        # no stdscr / no prompt
    assert calls['method'] == 'POST'
    assert calls['endpoint'].endswith('/accept')
    assert state.status.startswith('accepted')
    assert state.dirty is True


def test_do_respond_tentative_endpoint(monkeypatch):
    calls = {}
    monkeypatch.setattr(tui.api_mod, 'api_request',
                        lambda *a, **k: calls.update(endpoint=a[2]) or {'ok': True})
    state = _state([_event()])
    tui._do_respond(state, 'tentative')
    assert calls['endpoint'].endswith('/tentativelyaccept')


def test_do_respond_no_event_selected():
    state = _state([])
    tui._do_respond(state, 'accept')
    assert state.status == 'no event selected'


def test_do_respond_api_failure_reported(monkeypatch):
    monkeypatch.setattr(tui.api_mod, 'api_request', lambda *a, **k: None)
    state = _state([_event()])
    tui._do_respond(state, 'decline')
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
