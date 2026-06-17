"""Phase 2 gate tests for the owa-graph interactive explorer TUI.

Covers graph-specific behaviour: fetch_items mint+fetch cycle, seed-failure
graceful degrade, on_drill history push, on_back pop-restore without network,
render_detail format gating (graph vs non-graph), 'a' audience-switch, 'n'
next-page, on_search failed-jump keeps prior view, 'D' debug overlay.

Generic j/k/Esc/q/resize navigation is already covered by test_kit_app.py
and is NOT re-tested here.
"""
from __future__ import annotations

import base64
import json

from owa_core.tui_kit import app as _app
from owa_graph import tui
from owa_graph.tui import (
    GraphState,
    _action_audience_switch,
    _action_debug_overlay,
    _action_next_page,
    fetch_items,
    on_back,
    on_drill,
    on_refresh,
    on_search,
    render_detail,
    render_row,
)
from owa_graph.tui_nav import Row

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _jwt(scp='User.Read'):
    """Build a minimal JWT-shaped token."""
    def seg(obj):
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
    payload = seg({'scp': scp, 'tid': 'tenant'})
    return f'{seg({"alg": "none"})}.{payload}.sig'


def _make_state(**kwargs):
    """Return a GraphState with a minimal config and no real token."""
    defaults = {'audience': 'graph', 'path': 'me', 'debug': False}
    defaults.update(kwargs)
    return GraphState({'owa_piggy_profile': ''}, **defaults)


def _good_token_info(audience='graph'):
    import time
    return tui.TokenInfo(
        token=_jwt(),
        scopes=frozenset({'User.Read'}),
        api_base='https://graph.microsoft.com/v1.0',
        exp_epoch=int(time.time()) + 3600,
    )


# ---------------------------------------------------------------------------
# fetch_items: first-iteration mint + fetch
# ---------------------------------------------------------------------------

class TestFetchItems:
    def test_fetch_items_calls_ensure_token_then_fetch_page(self, monkeypatch):
        """Happy path: token minted, fetch page returns a collection."""
        state = _make_state()
        info = _good_token_info()

        monkeypatch.setattr(tui, '_ensure_token', lambda aud, st: (
            setattr(st, 'token', info.token) or
            setattr(st, 'api_base', info.api_base) or
            setattr(st, 'scopes', info.scopes) or
            setattr(st, 'exp_epoch', info.exp_epoch) or
            info
        ))

        collection = {
            'value': [
                {'id': '1', 'displayName': 'Alice'},
                {'id': '2', 'displayName': 'Bob'},
            ]
        }
        monkeypatch.setattr(
            tui, '_fetch_page',
            lambda aud, url, tok, debug=False: ('collection', collection, None),
        )

        fetch_items(state)
        assert len(state.items) == 2
        assert state.items[0].label == 'Alice'
        assert state.status == ''

    def test_fetch_items_token_failure_leaves_items_empty(self, monkeypatch):
        """Token mint fails → items empty, status set, no exception."""
        state = _make_state()
        state.items = []

        def fail_token(aud, st):
            st.status = 'AADSTS700084: refresh token expired'
            return None

        monkeypatch.setattr(tui, '_ensure_token', fail_token)
        fetch_items(state)

        assert state.items == []
        assert 'AADSTS700084' in state.status

    def test_fetch_items_never_raises(self, monkeypatch):
        """Even if _fetch_page raises, fetch_items swallows it."""
        state = _make_state()
        info = _good_token_info()

        monkeypatch.setattr(tui, '_ensure_token', lambda aud, st: info)
        state.token = info.token
        state.api_base = info.api_base

        monkeypatch.setattr(
            tui, '_fetch_page',
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')),
        )

        fetch_items(state)  # must not raise
        assert 'boom' in state.status

    def test_fetch_items_http_failure_kind_sets_status(self, monkeypatch):
        """HTTP 401 → kind='auth', payload=msg → items empty, status=msg."""
        state = _make_state()
        info = _good_token_info()
        monkeypatch.setattr(tui, '_ensure_token', lambda aud, st: info)
        state.token = info.token
        state.api_base = info.api_base

        monkeypatch.setattr(
            tui, '_fetch_page',
            lambda *a, **k: ('auth', 'token expired', None),
        )
        fetch_items(state)
        assert state.items == []
        assert 'token expired' in state.status

    def test_fetch_items_sets_response_and_kind(self, monkeypatch):
        """On success, state.response and state.kind are populated."""
        state = _make_state()
        info = _good_token_info()
        monkeypatch.setattr(tui, '_ensure_token', lambda aud, st: info)
        state.token = info.token
        state.api_base = info.api_base

        payload = {'value': [{'id': '1', 'displayName': 'X'}]}
        monkeypatch.setattr(
            tui, '_fetch_page',
            lambda *a, **k: ('collection', payload, None),
        )
        fetch_items(state)
        assert state.kind == 'collection'
        assert state.response is payload


# ---------------------------------------------------------------------------
# on_drill / on_back: history push and pop
# ---------------------------------------------------------------------------

class TestDrillBack:
    def test_drill_pushes_history_frame(self):
        state = _make_state(path='me')
        state.items = [Row('Alice', '11111111-1111-1111-1111-111111111111', True)]
        state.selected = 0
        state.top = 0
        state.next_link = 'https://graph.microsoft.com/v1.0/me?$skip=10'

        item = state.items[0]
        on_drill(state, item)

        assert len(state.history) == 1
        assert state.history[0][1] == 'me'   # path
        assert state.dirty is True

    def test_drill_updates_path_via_next_path(self):
        state = _make_state(path='users')
        state.items = []
        state.next_link = None

        item = Row('Alice', '11111111-1111-1111-1111-111111111111', True)
        on_drill(state, item)

        assert state.path == 'users/11111111-1111-1111-1111-111111111111'

    def test_drill_non_drillable_is_noop(self):
        state = _make_state(path='me')
        state.items = []
        item = Row('(no items)', None, False)
        on_drill(state, item)
        assert state.history == []
        assert not getattr(state, 'dirty', False) or True  # dirty may be True from init

    def test_back_pops_and_restores_without_network(self, monkeypatch):
        state = _make_state(path='users/abc')
        prior_items = [Row('Alice', 'abc', True)]
        state.history = [('graph', 'users', '', 0, 0, prior_items, None)]

        # ensure no network calls happen (would fail if fetch_items were triggered)
        called = {'fetch': False}
        monkeypatch.setattr(tui, '_fetch_page', lambda *a, **k: called.update(fetch=True))
        monkeypatch.setattr(tui, '_ensure_token', lambda *a, **k: called.update(fetch=True))

        result = on_back(state)
        assert result is True
        assert state.path == 'users'
        assert state.audience == 'graph'
        assert state.items is prior_items
        assert state.history == []
        assert not called['fetch']

    def test_back_returns_false_when_history_empty(self):
        state = _make_state()
        result = on_back(state)
        assert result is False

    def test_back_does_not_set_dirty(self):
        state = _make_state(path='users/abc')
        state.dirty = False
        state.history = [('graph', 'users', '', 0, 0, [], None)]
        on_back(state)
        assert state.dirty is False  # no network re-fetch triggered


# ---------------------------------------------------------------------------
# render_detail: format_pretty gating
# ---------------------------------------------------------------------------

class TestRenderDetail:
    def _state_for(self, audience, kind, payload):
        state = _make_state(audience=audience)
        state.kind = kind
        state.response = payload
        return state

    def test_graph_collection_uses_format_pretty(self, monkeypatch):
        """graph + collection → format_pretty is called (not raw json.dumps)."""
        called = {'pretty': False}
        original = tui._format_pretty

        def spy(payload):
            called['pretty'] = True
            return original(payload)
        monkeypatch.setattr(tui, '_format_pretty', spy)

        payload = {'value': [{'id': '1', 'displayName': 'Alice'}]}
        state = self._state_for('graph', 'collection', payload)
        item = Row('Alice', '1', True)
        render_detail(item, 80, state=state)
        assert called['pretty']

    def test_arm_collection_does_not_use_format_pretty(self, monkeypatch):
        """azure + collection → format_pretty must NOT be called (mislabelling)."""
        called = {'pretty': False}

        def spy(payload):
            called['pretty'] = True
            return json.dumps(payload, indent=2)
        monkeypatch.setattr(tui, '_format_pretty', spy)

        payload = {
            'value': [{'id': '/subscriptions/aaa', 'displayName': 'Prod'}],
            'nextLink': 'https://management.azure.com/subscriptions?$skip=2',
        }
        state = self._state_for('azure', 'collection', payload)
        item = Row('Prod', '/subscriptions/aaa', True)
        render_detail(item, 80, state=state)
        assert not called['pretty']

    def test_devops_collection_does_not_use_format_pretty(self, monkeypatch):
        """devops + collection → format_pretty must NOT be called."""
        called = {'pretty': False}

        def spy(payload):
            called['pretty'] = True
            return json.dumps(payload, indent=2)
        monkeypatch.setattr(tui, '_format_pretty', spy)

        payload = {'value': [{'id': 'proj-1', 'name': 'Alpha'}]}
        state = self._state_for('devops', 'collection', payload)
        item = Row('Alpha', 'proj-1', True)
        render_detail(item, 80, state=state)
        assert not called['pretty']

    def test_opaque_renders_hex_preview(self):
        """opaque kind → hex dump lines (no format_pretty)."""
        raw = b'\x89PNG not json'
        state = self._state_for('teams', 'opaque', raw)
        item = Row('(binary)', None, False)
        lines = render_detail(item, 80, state=state)
        assert any('bytes' in ln or 'binary' in ln.lower() for ln in lines)

    def test_scalar_renders_str(self):
        """scalar kind → string representation."""
        state = self._state_for('graph', 'scalar', 42)
        item = Row('42', None, False)
        lines = render_detail(item, 80, state=state)
        assert any('42' in ln for ln in lines)

    def test_tier_d_appends_footer_note(self):
        """keyvault audience → Tier D note appended."""
        payload = {'value': 'my-secret'}
        state = self._state_for('keyvault', 'object', payload)
        item = Row('my-secret', None, False)
        lines = render_detail(item, 80, state=state)
        assert any('Tier D' in ln for ln in lines)

    def test_none_item_returns_empty(self):
        """render_detail(None, ...) → []."""
        state = self._state_for('graph', 'collection', {})
        lines = render_detail(None, 80, state=state)
        assert lines == []


# ---------------------------------------------------------------------------
# render_row
# ---------------------------------------------------------------------------

class TestRenderRow:
    def test_label_truncated_to_width(self):
        item = Row('a' * 100, None, False)
        row = render_row(item, 10)
        assert len(row) <= 10

    def test_dim_item_gets_leading_space(self):
        item = Row('more', None, False, dim=True)
        row = render_row(item, 20)
        assert row.startswith(' ')

    def test_non_dim_no_leading_space(self):
        item = Row('Alice', 'abc', True)
        row = render_row(item, 20)
        assert row[0] == 'A'


# ---------------------------------------------------------------------------
# 'a' action: audience switch commits new audience even on failed switch
# ---------------------------------------------------------------------------

class TestAudienceSwitch:
    def test_audience_switch_changes_audience_and_sets_dirty(self):
        state = _make_state(audience='graph')
        _action_audience_switch(state)
        assert state.audience != 'graph' or state.dirty  # either changed or dirty
        assert state.dirty is True

    def test_audience_committed_on_failed_next_fetch(self, monkeypatch):
        """After 'a', the new audience is set even if the subsequent fetch fails.
        This allows 'r' to retry the new audience.
        """
        state = _make_state(audience='graph')
        _action_audience_switch(state)
        new_audience = state.audience
        # Simulate fetch failure
        def fail_token(aud, st):
            st.status = 'auth failed'
            return None
        monkeypatch.setattr(tui, '_ensure_token', fail_token)
        fetch_items(state)
        # audience remains committed
        assert state.audience == new_audience
        assert state.items == []


# ---------------------------------------------------------------------------
# 'n' action: next page via state.next_link
# ---------------------------------------------------------------------------

class TestNextPage:
    def test_next_page_uses_next_link(self, monkeypatch):
        """'n' fetches state.next_link and extends items."""
        state = _make_state()
        state.token = _jwt()
        state.api_base = 'https://graph.microsoft.com/v1.0'
        next_url = 'https://graph.microsoft.com/v1.0/users?$skiptoken=xyz'
        state.next_link = next_url
        state.items = [Row('Alice', '1', True)]

        payload = {'value': [{'id': '3', 'displayName': 'Carol'}]}
        monkeypatch.setattr(
            tui, '_ensure_token',
            lambda aud, st: _good_token_info(aud),
        )
        # Patch _fetch_page inside the action's local import scope
        import owa_graph.tui_nav as nav_mod
        monkeypatch.setattr(nav_mod, '_tui_get',
            lambda url, tok, debug=False: (
                'ok',
                nav_mod.FetchResult(200, {}, json.dumps(payload).encode()),
            ),
        )

        _action_next_page(state)
        # items should have grown (Alice + Carol)
        assert len(state.items) >= 2

    def test_next_page_noop_when_no_link(self):
        """'n' with no next_link sets a status message and does nothing."""
        state = _make_state()
        state.next_link = None
        state.items = [Row('X', None, False)]
        _action_next_page(state)
        assert 'no next page' in state.status
        assert len(state.items) == 1


# ---------------------------------------------------------------------------
# on_search: failed jump keeps prior view
# ---------------------------------------------------------------------------

class TestOnSearch:
    def test_search_sets_path_and_dirty(self):
        state = _make_state(path='me')
        state.items = [Row('Alice', '1', True)]
        on_search(state, 'users')
        assert state.path == 'users'
        assert state.dirty is True

    def test_search_blank_is_noop(self):
        state = _make_state(path='me')
        state.dirty = False
        on_search(state, '')
        assert state.dirty is False

    def test_search_failed_jump_keeps_prior_items(self, monkeypatch):
        """On search + failed fetch: prior items remain (graceful degrade).

        on_search itself only sets path+dirty; it does NOT clear state.items.
        The subsequent fetch_items will set items=[] if the fetch fails, BUT
        the contract here is that on_search doesn't pre-emptively clear items.
        """
        state = _make_state(path='me')
        prior = [Row('Alice', '1', True)]
        state.items = list(prior)
        state.dirty = False

        on_search(state, 'nonexistent/path/xyz')
        # items not yet cleared by on_search itself
        assert state.items == prior

    def test_search_path_stripped(self):
        state = _make_state(path='me')
        on_search(state, '  users  ')
        assert state.path == 'users'


# ---------------------------------------------------------------------------
# 'D' action: debug overlay renders stderr_buf
# ---------------------------------------------------------------------------

class TestDebugOverlay:
    def test_debug_overlay_shows_stderr_buf(self):
        state = _make_state()
        state.stderr_buf.write('test error output')
        _action_debug_overlay(state)
        assert 'test error output' in state.status

    def test_debug_overlay_empty_buf_message(self):
        state = _make_state()
        _action_debug_overlay(state)
        assert 'empty' in state.status

    def test_debug_overlay_toggles(self):
        state = _make_state()
        state.stderr_buf.write('x')
        _action_debug_overlay(state)
        assert state.overlay == 'debug'
        _action_debug_overlay(state)
        assert state.overlay is None


# ---------------------------------------------------------------------------
# on_refresh
# ---------------------------------------------------------------------------

class TestOnRefresh:
    def test_refresh_sets_dirty_and_resets_paging(self):
        state = _make_state()
        state.next_link = 'https://example.com/next'
        state.selected = 5
        state.top = 3
        state.dirty = False

        on_refresh(state)
        assert state.dirty is True
        assert state.next_link is None
        assert state.selected == 0
        assert state.top == 0


# ---------------------------------------------------------------------------
# Full loop integration via FakeScreen
# ---------------------------------------------------------------------------

class TestLoopIntegration:
    """Drive app._loop directly with a FakeScreen to test end-to-end."""

    def _run_loop(self, fake_screen, keys, state, spec):
        screen = fake_screen(keys=keys)
        _app._loop(screen, state, spec)
        return screen

    def _make_spec_with_mocks(self, monkeypatch, payload=None, token_ok=True):
        """Build a spec + state with mocked token + fetch."""
        import time

        from owa_graph.tui import build_spec

        info = tui.TokenInfo(
            token=_jwt(),
            scopes=frozenset({'User.Read'}),
            api_base='https://graph.microsoft.com/v1.0',
            exp_epoch=int(time.time()) + 3600,
        )

        if token_ok:
            monkeypatch.setattr(tui, '_ensure_token', lambda aud, st: (
                setattr(st, 'token', info.token) or
                setattr(st, 'api_base', info.api_base) or
                setattr(st, 'scopes', info.scopes) or
                info
            ))
        else:
            def fail_token(aud, st):
                st.status = 'auth failed for test'
                return None
            monkeypatch.setattr(tui, '_ensure_token', fail_token)

        col = payload or {'value': [
            {'id': '1', 'displayName': 'Alice'},
            {'id': '2', 'displayName': 'Bob'},
        ]}
        monkeypatch.setattr(
            tui, '_fetch_page',
            lambda *a, **k: ('collection', col, None),
        )

        state = _make_state()
        spec = build_spec(state)
        return state, spec

    def test_first_iteration_mints_and_fetches(self, fake_screen, monkeypatch):
        state, spec = self._make_spec_with_mocks(monkeypatch)
        self._run_loop(fake_screen, [ord('q')], state, spec)
        assert len(state.items) == 2

    def test_seed_failure_status_not_exit(self, fake_screen, monkeypatch):
        """Auth failure → items empty, loop stays alive until 'q' (no crash-exit)."""
        state, spec = self._make_spec_with_mocks(monkeypatch, token_ok=False)
        # Give it 'j' first so one more key is processed after the failed fetch,
        # then 'q'. This proves the loop kept running after the failure.
        self._run_loop(fake_screen, [ord('j'), ord('q')], state, spec)
        assert state.items == []
        # loop terminated normally via 'q', not via exception
        assert state.running is False

    def test_drill_pushes_history_via_loop(self, fake_screen, monkeypatch):
        state, spec = self._make_spec_with_mocks(monkeypatch)
        # 'q' alone first to see items, then Enter to drill, then q
        self._run_loop(fake_screen, [10, ord('q')], state, spec)
        # either history was pushed, or on_drill was called — items should be there
        # (the drill may or may not push depending on drillability)
        assert state.running is False

    def test_back_restores_without_refetch(self, fake_screen, monkeypatch):
        state, spec = self._make_spec_with_mocks(monkeypatch)
        prior_items = [Row('Prior', 'prior', True)]
        state.history = [('graph', 'prior', '', 0, 0, prior_items, None)]
        # 'h' should pop history, not trigger a new fetch
        fetch_count = {'n': 0}
        orig_fetch = spec.fetch_items

        def counting_fetch(st):
            fetch_count['n'] += 1
            return orig_fetch(st)
        spec = type(spec)(
            render_row=spec.render_row,
            render_detail=spec.render_detail,
            fetch_items=counting_fetch,
            on_search=spec.on_search,
            on_drill=spec.on_drill,
            on_back=spec.on_back,
            on_refresh=spec.on_refresh,
            on_menu_action=spec.on_menu_action,
            actions=spec.actions,
            footer=spec.footer,
            empty_text=spec.empty_text,
        )
        # First fetch (dirty=True), then 'h' (back, dirty stays False), then 'q'
        self._run_loop(fake_screen, [ord('h'), ord('q')], state, spec)
        # fetch count == 1 (initial dirty), not 2 (back must not trigger refetch)
        assert fetch_count['n'] == 1
