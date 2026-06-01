"""Tests for the owa-sites two-audience auth (host discovery + scope override)."""
import json

import pytest

from owa_core import auth as core_auth
from owa_core.errors import AuthExpiredError, ExitCode, InternalError
from owa_core.http import Response
from owa_sites import auth as auth_mod


class FakeProc:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_owa_piggy(monkeypatch, fake_run, available=True):
    monkeypatch.setattr(
        core_auth.shutil, 'which',
        lambda name: '/usr/bin/owa-piggy' if available else None,
    )
    monkeypatch.setattr(core_auth.subprocess, 'run', fake_run)


def _ok_run(argv, *args, **kwargs):
    if argv == ['owa-piggy', '--version']:
        return FakeProc(stdout='owa-piggy 0.7.1\n')
    return FakeProc(stdout=json.dumps({'access_token': 'fake-access-token-for-tests'}))


def _org_resp(domains=('foo.com', 'CasaDamsleth.onmicrosoft.com')):
    return Response(
        status=200, headers={},
        json={'value': [{'verifiedDomains': [{'name': d} for d in domains]}]},
        bytes=b'',
    )


def test_resolve_sp_host_discovers_from_organization(monkeypatch):
    _patch_owa_piggy(monkeypatch, _ok_run)
    monkeypatch.setattr(auth_mod.http, 'request', lambda *a, **k: _org_resp())
    assert auth_mod.resolve_sp_host({}, debug=False) == 'casadamsleth.sharepoint.com'


def test_resolve_sp_host_pinned_skips_discovery(monkeypatch):
    monkeypatch.setattr(
        auth_mod.http, 'request', lambda *a, **k: pytest.fail('discovery should be skipped')
    )
    host = auth_mod.resolve_sp_host({'sharepoint_host': 'https://Contoso.sharepoint.com/'}, debug=False)
    assert host == 'contoso.sharepoint.com'


def test_resolve_sp_host_raises_without_onmicrosoft_domain(monkeypatch):
    _patch_owa_piggy(monkeypatch, _ok_run)
    monkeypatch.setattr(auth_mod.http, 'request', lambda *a, **k: _org_resp(('foo.com',)))
    with pytest.raises(InternalError):
        auth_mod.resolve_sp_host({}, debug=False)


def test_setup_auth_returns_sharepoint_base(monkeypatch):
    _patch_owa_piggy(monkeypatch, _ok_run)
    monkeypatch.setattr(auth_mod.http, 'request', lambda *a, **k: _org_resp())
    access, base = auth_mod.setup_auth({}, debug=False)
    assert access == 'fake-access-token-for-tests'
    assert base == 'https://casadamsleth.sharepoint.com'


def test_setup_auth_pinned_host_no_discovery(monkeypatch):
    _patch_owa_piggy(monkeypatch, _ok_run)
    monkeypatch.setattr(
        auth_mod.http, 'request', lambda *a, **k: pytest.fail('discovery should be skipped')
    )
    access, base = auth_mod.setup_auth({'sharepoint_host': 'contoso.sharepoint.com'}, debug=False)
    assert base == 'https://contoso.sharepoint.com'


def test_do_token_refresh_failure_returns_none(monkeypatch, capsys):
    _patch_owa_piggy(monkeypatch, lambda *a, **k: FakeProc(), available=False)
    assert auth_mod.do_token_refresh({}, debug=False) is None
    assert 'owa-piggy not found' in capsys.readouterr().err


def test_setup_auth_raises_when_broker_missing(monkeypatch):
    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: None)
    with pytest.raises(AuthExpiredError) as exc:
        auth_mod.setup_auth({'sharepoint_host': 'contoso.sharepoint.com'}, debug=False)
    assert exc.value.exit_code == ExitCode.AUTH_EXPIRED
