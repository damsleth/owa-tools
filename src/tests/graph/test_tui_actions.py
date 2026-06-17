"""Tests for the owa-graph TUI action callbacks, render_detail branches, the
menu, and the run() lifecycle (Phase 2, Agent C1).

These complement test_tui_loop.py (which drives the fetch/nav cycle) by
exercising the keybinding actions directly — with a focus on the curses-safe
invariant: clipboard/browser actions must never let a child process write to
the real terminal fds, and no action may raise out of the loop.
"""
from __future__ import annotations

import contextlib

import pytest

from owa_graph import tui, tui_settings
from owa_graph.tui import TokenInfo


def _state(audience='graph', path='me'):
    state = tui.GraphState({}, audience=audience, path=path,
                           settings=tui_settings.DEFAULTS)
    state.api_base = 'https://graph.microsoft.com/v1.0'
    state.token = 'tok'
    return state


# ---------------------------------------------------------------------------
# Clipboard / browser — the headless-safety (curses-safe fd) paths
# ---------------------------------------------------------------------------

def test_yank_uses_capture_output(monkeypatch):
    calls = {}

    def fake_run(argv, **kwargs):
        calls['argv'] = argv
        calls['kwargs'] = kwargs
        return None
    monkeypatch.setattr(tui.subprocess, 'run', fake_run)
    state = _state()
    tui._action_yank_url(state)
    # capture_output keeps xclip/xsel diagnostics off the terminal fd.
    assert calls['kwargs'].get('capture_output') is True
    assert state.status.startswith('yanked:')


def test_yank_falls_back_when_no_clipboard(monkeypatch):
    def fake_run(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(tui.subprocess, 'run', fake_run)
    state = _state()
    tui._action_yank_url(state)
    assert state.status.startswith('url:')  # never raises, shows the URL


def test_open_browser_non_graph_is_noop():
    state = _state(audience='azure')
    tui._action_open_browser(state)
    assert 'no browser target' in state.status


def test_open_browser_graph_silences_fds(monkeypatch):
    opened = {}
    # Neutralise the fd dance under pytest's own fd capture; we only assert
    # the status logic here (the real fd silencing is exercised in prod).
    monkeypatch.setattr(tui._screen, 'silence_os_fds', contextlib.nullcontext)
    monkeypatch.setattr(tui.webbrowser, 'open', lambda url: opened.setdefault('url', url) or True)
    state = _state()
    tui._action_open_browser(state)
    assert 'graph-explorer' in opened['url']
    assert state.status.startswith('opened:')


def test_open_browser_reports_no_browser(monkeypatch):
    monkeypatch.setattr(tui._screen, 'silence_os_fds', contextlib.nullcontext)
    monkeypatch.setattr(tui.webbrowser, 'open', lambda url: False)
    state = _state()
    tui._action_open_browser(state)
    assert state.status == 'no browser available'


# ---------------------------------------------------------------------------
# Other actions
# ---------------------------------------------------------------------------

def test_render_curl_sets_status_and_buffer():
    state = _state()
    tui._action_render_curl(state)
    assert state.status
    assert 'curl:' in state.stderr_buf.getvalue()


def test_bookmark_adds_and_dedupes():
    state = _state(path='users')
    tui._action_bookmark(state)
    marks = tui_settings.parse_bookmarks(state.settings.bookmarks)
    assert {'audience': 'graph', 'path': 'users', 'label': ''} in marks
    tui._action_bookmark(state)  # same (audience,path) again
    assert len(tui_settings.parse_bookmarks(state.settings.bookmarks)) == 1


def test_edit_query_hint():
    state = _state()
    tui._action_edit_query(state)
    assert state.status


def test_debug_overlay_empty_and_populated():
    state = _state()
    tui._action_debug_overlay(state)
    assert 'empty' in state.status
    state.stderr_buf.write('boom trace\n')
    tui._action_debug_overlay(state)
    assert 'boom' in state.status


def test_audience_switch_cycles_and_marks_dirty():
    state = _state(audience='graph')
    tui._action_audience_switch(state)
    assert state.audience != 'graph'
    assert state.dirty is True


def test_next_page_no_link():
    state = _state()
    state.next_link = None
    tui._action_next_page(state)
    assert state.status == 'no next page'


def test_next_page_extends_items(monkeypatch):
    state = _state()
    state.next_link = 'https://graph.microsoft.com/v1.0/users?$skip=2'
    state.items = []
    monkeypatch.setattr(tui, '_ensure_token',
                        lambda aud, st: TokenInfo('t', frozenset(), st.api_base, 9999999999))
    monkeypatch.setattr(tui, '_fetch_page',
                        lambda aud, url, tok, debug=False: ('collection', {'value': [{'id': 'x'}]}, None))
    tui._action_next_page(state)
    assert state.items
    assert state.status.startswith('+')


def test_on_menu_action_opens_overlay():
    state = _state()
    assert tui.on_menu_action(state, 'open_audiences') is False
    assert state.overlay == 'audiences'
    assert tui.on_menu_action(state, 'unknown') is False


# ---------------------------------------------------------------------------
# render_detail branches
# ---------------------------------------------------------------------------

def test_render_detail_none_item():
    assert tui.render_detail(None, 40, state=_state()) == []


def test_render_detail_opaque_hex():
    state = _state()
    state.kind = 'opaque'
    state.response = b'\x00\x01\x02binary'
    lines = tui.render_detail(object(), 80, state=state)
    assert any('binary / non-JSON' in ln for ln in lines)


def test_render_detail_graph_uses_format_pretty(monkeypatch):
    state = _state(audience='graph')
    state.kind = 'collection'
    state.response = {'value': []}
    called = {}

    def fake_pretty(payload):
        called['hit'] = True
        return 'PRETTY'
    monkeypatch.setattr(tui, '_format_pretty', fake_pretty)
    lines = tui.render_detail(object(), 80, state=state)
    assert called.get('hit')
    assert 'PRETTY' in '\n'.join(lines)


def test_render_detail_non_graph_skips_format_pretty(monkeypatch):
    state = _state(audience='azure')
    state.kind = 'collection'
    state.response = {'value': [{'id': '/subscriptions/x'}]}
    monkeypatch.setattr(tui, '_format_pretty',
                        lambda p: pytest.fail('format_pretty must not run for non-graph'))
    lines = tui.render_detail(object(), 80, state=state)
    assert any('subscriptions' in ln for ln in lines)


def test_render_detail_tier_d_note():
    state = _state(audience='keyvault')
    state.kind = 'object'
    state.response = {'k': 'v'}
    lines = tui.render_detail(object(), 80, state=state)
    assert any('Tier D' in ln for ln in lines)


# ---------------------------------------------------------------------------
# Menu + run lifecycle
# ---------------------------------------------------------------------------

def test_build_menu_has_seven_settings_fields():
    from owa_graph.tui_menu import build_menu
    menu = build_menu()
    assert len(menu._settings_fields) == 7   # M2: bookmarks included
    rows = menu.items_for_settings(tui_settings.DEFAULTS)
    assert any(r.startswith('Bookmarks JSON') for r in rows)
    out = menu.render(80, 24, tui_settings.DEFAULTS)
    assert len(out) == 24
    assert any('owa-graph' in ln for ln in out)


def test_run_restores_stderr(monkeypatch):
    import sys
    seen = {}

    def fake_app_run(spec, state):
        seen['audience'] = state.audience
        seen['detail_callable'] = spec.render_detail(object(), 40) == []  # state-bound, no item
    monkeypatch.setattr(tui._app, 'run', fake_app_run)
    before = sys.stderr
    tui.run({}, start_audience='graph')
    assert sys.stderr is before        # restored
    assert seen['audience'] == 'graph'


def test_run_restores_stderr_on_exception(monkeypatch):
    import sys

    def boom(spec, state):
        raise RuntimeError('loop blew up')
    monkeypatch.setattr(tui._app, 'run', boom)
    before = sys.stderr
    with pytest.raises(RuntimeError):
        tui.run({}, start_audience='graph')
    assert sys.stderr is before        # finally restored it
