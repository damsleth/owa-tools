"""Gate tests for the owa-graph TUI auth/token-cache core (Phase 1, A2).

Exercises _ensure_token's curses-safe FOCI boundary: exp-aware per-audience
caching, no double-mint on a hit, graceful failure (None + status + eviction),
the expires_at=None TTL fallback, and that TokenInfo carries api_base + scopes
(scopes decoded from the token's `scp` claim, not the broker's requested scope).
"""
from __future__ import annotations

import base64
import json
import time

import pytest

from owa_core.auth import BrokerToken
from owa_core.errors import AuthExpiredError
from owa_graph import tui


def _jwt_with_scopes(scp):
    """Build a JWT-shaped access token whose payload carries `scp`."""
    def seg(obj):
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
    payload = seg({'scp': scp, 'tid': 'tenant-123'})
    return f'{seg({"alg": "none"})}.{payload}.sig'


def _broker(access, *, expires_at=None, expires_in=3600):
    return BrokerToken(
        access_token=access,
        audience='graph',
        expires_at=expires_at,
        expires_in=expires_in,
        scope='https://graph.microsoft.com/.default',
    )


@pytest.fixture
def state():
    return tui.GraphState({'owa_piggy_profile': ''}, audience='graph')


def test_cache_hit_does_not_remint(monkeypatch, state):
    info = tui.TokenInfo(
        token='cached', scopes=frozenset({'User.Read'}),
        api_base='https://graph.microsoft.com/v1.0',
        exp_epoch=int(time.time()) + 3600,
    )
    state.token_cache['graph'] = info

    def boom(*a, **k):
        raise AssertionError('must not mint on a cache hit')
    monkeypatch.setattr(tui, 'get_token_for_config', boom)

    out = tui._ensure_token('graph', state)
    assert out is info
    assert state.token == 'cached'


def test_miss_mints_and_populates(monkeypatch, state):
    token = _jwt_with_scopes('User.Read Mail.Read')
    monkeypatch.setattr(tui, 'get_token_for_config', lambda *a, **k: _broker(token))
    info = tui._ensure_token('graph', state)
    assert info is not None
    assert info.token == token
    assert info.api_base == 'https://graph.microsoft.com/v1.0'
    assert info.scopes == frozenset({'User.Read', 'Mail.Read'})
    # session context updated atomically
    assert state.token == token
    assert state.api_base == info.api_base
    assert state.scopes == info.scopes
    assert state.token_cache['graph'] is info


def test_failure_returns_none_status_and_evicts(monkeypatch, state):
    # Prime a stale entry to prove failure evicts (so `r` re-attempts).
    state.token_cache['graph'] = tui.TokenInfo('old', frozenset(), 'x', 0)

    def fail(*a, **k):
        raise AuthExpiredError('refresh token expired (AADSTS700084)')
    monkeypatch.setattr(tui, 'get_token_for_config', fail)

    out = tui._ensure_token('graph', state)
    assert out is None
    assert 'graph' not in state.token_cache
    assert 'AADSTS700084' in state.status  # the redacted failure surfaces as status


def test_per_audience_keying(monkeypatch, state):
    graph_token = _jwt_with_scopes('User.Read')
    state.token_cache['graph'] = tui.TokenInfo(
        graph_token, frozenset({'User.Read'}),
        'https://graph.microsoft.com/v1.0', int(time.time()) + 3600,
    )
    minted = {}

    def mint(config, *, tool_name, audience, debug=False):
        minted['audience'] = audience
        return _broker(_jwt_with_scopes('x'))
    monkeypatch.setattr(tui, 'get_token_for_config', mint)

    # A cached 'graph' must not satisfy an 'azure' request.
    info = tui._ensure_token('azure', state)
    assert minted['audience'] == 'azure'
    assert info.api_base == 'https://management.azure.com'
    assert state.audience == 'azure'


def test_expiry_forces_remint(monkeypatch, state):
    state.token_cache['graph'] = tui.TokenInfo(
        'expired', frozenset(), 'https://graph.microsoft.com/v1.0',
        int(time.time()) - 10,  # already past
    )
    fresh = _jwt_with_scopes('User.Read')
    monkeypatch.setattr(tui, 'get_token_for_config', lambda *a, **k: _broker(fresh))
    info = tui._ensure_token('graph', state)
    assert info.token == fresh


def test_expires_at_none_uses_ttl_without_raising(monkeypatch, state):
    token = _jwt_with_scopes('User.Read')
    monkeypatch.setattr(
        tui, 'get_token_for_config',
        lambda *a, **k: _broker(token, expires_at=None, expires_in=None),
    )
    before = time.time()
    info = tui._ensure_token('graph', state)
    assert info is not None
    # Concrete int epoch ~ now + default TTL (never None).
    assert isinstance(info.exp_epoch, int)
    assert before < info.exp_epoch <= before + tui._DEFAULT_TTL + 2
