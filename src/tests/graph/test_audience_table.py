"""The audience table and its seed entry points must stay in lockstep
with owa-piggy's KNOWN_AUDIENCES. We pin the expected short-name set as a
literal snapshot rather than importing owa_piggy: the installed broker may
lag the table we ship, and this test is what flags that drift.
"""
import base64
import json
from pathlib import Path

import pytest

from owa_core import jwt as jwt_mod
from owa_graph.auth import AUDIENCE_API_BASE, AUDIENCE_DESC, resolve_api_base

# owa-piggy 0.16.2 scopes.py:KNOWN_AUDIENCES (snapshot 2026-06-16).
# SharePoint is a *template* audience in owa-piggy, not a KNOWN_AUDIENCES
# entry, so it is deliberately absent.
_KNOWN_PIGGY_AUDIENCES = frozenset({
    'outlook', 'graph', 'teams', 'ic3', 'csa', 'presence', 'uis',
    'azure', 'keyvault', 'storage', 'sql', 'outlook365', 'substrate',
    'manage', 'powerbi', 'flow', 'devops',
})

_SEEDS_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / 'owa_graph' / 'data' / 'audience_seeds.json'
)


def _load_seeds():
    with open(_SEEDS_PATH, encoding='utf-8') as f:
        return json.load(f)


def test_audience_table_matches_piggy_known_audiences():
    assert set(AUDIENCE_API_BASE) == _KNOWN_PIGGY_AUDIENCES


def test_audience_desc_covers_all_audiences():
    assert set(AUDIENCE_DESC) == _KNOWN_PIGGY_AUDIENCES


@pytest.mark.parametrize('audience', sorted(_KNOWN_PIGGY_AUDIENCES))
def test_resolve_api_base_is_https(audience):
    assert resolve_api_base(audience).startswith('https://')


def test_every_audience_has_at_least_one_seed():
    seeds = _load_seeds()
    for audience in _KNOWN_PIGGY_AUDIENCES:
        assert audience in seeds, f'missing seed for {audience!r}'
        entries = seeds[audience]
        assert isinstance(entries, list) and entries, (
            f'{audience!r} must have >=1 seed entry'
        )
        for entry in entries:
            assert 'path' in entry and 'label' in entry, (
                f'{audience!r} seed entry needs path+label: {entry!r}'
            )


# --- owa_core.jwt.tenant_id ------------------------------------------------

def _make_payload_token(payload):
    seg = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b'=').decode()
    return f'header.{seg}.sig'


def test_tenant_id_returns_tid_claim():
    tok = _make_payload_token({'tid': '11111111-2222-3333-4444-555555555555'})
    assert jwt_mod.tenant_id(tok) == '11111111-2222-3333-4444-555555555555'


def test_tenant_id_falls_back_when_no_tid():
    tok = _make_payload_token({'foo': 'bar'})
    assert jwt_mod.tenant_id(tok) == 'myorganization'


def test_tenant_id_falls_back_on_garbage():
    assert jwt_mod.tenant_id('not.a.token') == 'myorganization'
    assert jwt_mod.tenant_id('') == 'myorganization'
