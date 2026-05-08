"""Pre-flight scope hint emitted by cmd_request.

Best-effort feature: warns on stderr when the request's required scope
is missing from the token's `scp` claim, then continues with the call
unchanged. Suppressed for non-graph audiences and when
OWA_GRAPH_NO_SCOPE_HINTS=1.
"""
import base64
import json
import sys

import pytest

from owa_graph import cli
from owa_graph import scopes as scopes_mod


def _make_token(scopes_str):
    payload = {'scp': scopes_str} if scopes_str else {}
    seg = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b'=').decode()
    return f'header.{seg}.sig'


@pytest.fixture
def in_scope_token():
    return _make_token('User.Read offline_access')


@pytest.fixture
def out_of_scope_token():
    return _make_token('Mail.Read')  # token has Mail.Read; we'll request /me which needs User.Read


@pytest.fixture(autouse=True)
def _reset_scope_cache():
    scopes_mod.reset_cache_for_tests()
    yield
    scopes_mod.reset_cache_for_tests()


def _stub_auth(monkeypatch, token):
    monkeypatch.setattr(
        cli.auth_mod, 'setup_auth',
        lambda _c, audience='graph', beta=False, debug=False:
        (token, 'https://graph.microsoft.com/v1.0'),
    )
    monkeypatch.setattr(
        cli.config_mod, 'load_config',
        lambda: {'default_audience': 'graph'},
    )
    monkeypatch.setattr(
        cli.api_mod, 'api_request',
        lambda *a, **k: {'displayName': 'Kim'},
    )


def _run(monkeypatch, *args):
    monkeypatch.setattr(sys, 'argv', ['owa-graph', *args])
    return cli.main()


def test_no_warning_when_scope_present(monkeypatch, capsys, in_scope_token):
    _stub_auth(monkeypatch, in_scope_token)
    rc = _run(monkeypatch, 'GET', '/me')
    err = capsys.readouterr().err
    assert rc == 0
    assert 'warn:' not in err


def test_warning_when_scope_missing(monkeypatch, capsys, out_of_scope_token):
    _stub_auth(monkeypatch, out_of_scope_token)
    rc = _run(monkeypatch, 'GET', '/me')
    err = capsys.readouterr().err
    assert rc == 0  # warning never blocks
    assert 'warn:' in err
    assert 'User.Read' in err
    assert 'OWA_GRAPH_NO_SCOPE_HINTS' in err


def test_warning_suppressed_by_env_var(monkeypatch, capsys, out_of_scope_token):
    monkeypatch.setenv('OWA_GRAPH_NO_SCOPE_HINTS', '1')
    _stub_auth(monkeypatch, out_of_scope_token)
    rc = _run(monkeypatch, 'GET', '/me')
    err = capsys.readouterr().err
    assert rc == 0
    assert 'warn:' not in err


def test_warning_suppressed_for_non_graph_audience(monkeypatch, capsys, out_of_scope_token):
    # Non-graph audiences (outlook, teams, etc.) use entirely different
    # scope namespaces; the manifest only covers Graph, so the hint
    # would be false-positive. Confirm we silence it.
    monkeypatch.setattr(
        cli.auth_mod, 'setup_auth',
        lambda _c, audience='graph', beta=False, debug=False:
        (out_of_scope_token, 'https://outlook.office.com/api/v2.0'),
    )
    monkeypatch.setattr(
        cli.config_mod, 'load_config',
        lambda: {'default_audience': 'graph'},
    )
    monkeypatch.setattr(
        cli.api_mod, 'api_request', lambda *a, **k: {'value': []},
    )
    rc = _run(monkeypatch, 'GET', '/me', '--audience', 'outlook')
    err = capsys.readouterr().err
    assert rc == 0
    assert 'warn:' not in err


def test_no_warning_for_uncovered_path(monkeypatch, capsys, out_of_scope_token):
    # The manifest has no entry for /something/random, so we don't
    # bug the user about scopes we don't know about.
    _stub_auth(monkeypatch, out_of_scope_token)
    rc = _run(monkeypatch, 'GET', '/something/random/we/never/curated')
    err = capsys.readouterr().err
    assert rc == 0
    assert 'warn:' not in err


def test_no_warning_in_curl_emit_mode(monkeypatch, capsys, out_of_scope_token):
    # --curl renders a command for the user to run elsewhere; warning
    # about scopes here would be premature.
    _stub_auth(monkeypatch, out_of_scope_token)
    rc = _run(monkeypatch, 'GET', '/me', '--curl')
    captured = capsys.readouterr()
    assert rc == 0
    assert 'warn:' not in captured.err
    assert 'curl' in captured.out


def test_warning_when_path_template_matches(monkeypatch, capsys, out_of_scope_token):
    # Concrete /users/{uuid}/manager should match the templated entry
    # /users/{id}/manager and surface User.Read.All as the missing scope.
    _stub_auth(monkeypatch, out_of_scope_token)
    rc = _run(monkeypatch, 'GET', '/users/00000000-0000-0000-0000-000000000000/manager')
    err = capsys.readouterr().err
    assert rc == 0
    assert 'User.Read.All' in err
