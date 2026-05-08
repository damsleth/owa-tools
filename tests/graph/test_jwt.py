"""jwt.py is tiny - test the happy path and the failure-tolerant
fallback explicitly so a regression in either is caught."""
import base64
import json
import time

from owa_core import jwt as jwt_mod


def _make_token(exp_offset_seconds):
    payload = {'exp': int(time.time()) + exp_offset_seconds}
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b'=').decode()
    return f'header.{encoded}.sig'


def test_decode_jwt_segment_round_trip():
    raw = json.dumps({'a': 1, 'b': 'two'}).encode()
    seg = base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
    assert jwt_mod.decode_jwt_segment(seg) == {'a': 1, 'b': 'two'}


def test_token_minutes_remaining_positive():
    tok = _make_token(3600)
    out = jwt_mod.token_minutes_remaining(tok)
    assert out is not None
    assert 58 <= out <= 60


def test_token_minutes_remaining_negative_for_expired():
    tok = _make_token(-3600)
    out = jwt_mod.token_minutes_remaining(tok)
    assert out is not None and out < 0


def test_token_minutes_remaining_handles_garbage():
    assert jwt_mod.token_minutes_remaining('not.a.token') is None
    assert jwt_mod.token_minutes_remaining('') is None
    assert jwt_mod.token_minutes_remaining('a.b') is None


def test_token_minutes_remaining_no_exp_claim():
    seg = base64.urlsafe_b64encode(json.dumps({'foo': 'bar'}).encode()).rstrip(b'=').decode()
    tok = f'header.{seg}.sig'
    assert jwt_mod.token_minutes_remaining(tok) is None


def _make_payload_token(payload):
    seg = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b'=').decode()
    return f'header.{seg}.sig'


def test_scopes_in_token_parses_scp_claim():
    tok = _make_payload_token({'scp': 'Mail.Read User.Read offline_access'})
    assert jwt_mod.scopes_in_token(tok) == {'Mail.Read', 'User.Read', 'offline_access'}


def test_scopes_in_token_parses_roles_for_app_only_tokens():
    tok = _make_payload_token({'roles': ['Mail.ReadWrite.All', 'User.Read.All']})
    assert jwt_mod.scopes_in_token(tok) == {'Mail.ReadWrite.All', 'User.Read.All'}


def test_scopes_in_token_merges_scp_and_roles():
    tok = _make_payload_token({
        'scp': 'User.Read',
        'roles': ['Mail.ReadWrite.All'],
    })
    assert jwt_mod.scopes_in_token(tok) == {'User.Read', 'Mail.ReadWrite.All'}


def test_scopes_in_token_returns_empty_on_garbage():
    assert jwt_mod.scopes_in_token('not.a.token') == set()
    assert jwt_mod.scopes_in_token('') == set()


def test_scopes_in_token_returns_empty_when_no_scope_claims():
    tok = _make_payload_token({'foo': 'bar'})
    assert jwt_mod.scopes_in_token(tok) == set()


def test_scope_in_token_predicate():
    tok = _make_payload_token({'scp': 'Mail.Read User.Read'})
    assert jwt_mod.scope_in_token(tok, 'Mail.Read')
    assert not jwt_mod.scope_in_token(tok, 'Mail.ReadWrite')
