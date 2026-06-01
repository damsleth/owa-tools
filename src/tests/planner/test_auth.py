"""Tests for the owa-planner auth bridge to owa-piggy."""
import json

import pytest

from owa_core import auth as core_auth
from owa_core.errors import AuthExpiredError, ExitCode
from owa_planner import auth as auth_mod


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


def test_do_token_refresh_returns_access_token(monkeypatch):
    _patch_owa_piggy(monkeypatch, _ok_run)
    assert auth_mod.do_token_refresh({}, debug=False) == 'fake-access-token-for-tests'


def test_do_token_refresh_failure_returns_none(monkeypatch, capsys):
    _patch_owa_piggy(monkeypatch, lambda *a, **k: FakeProc(), available=False)
    assert auth_mod.do_token_refresh({}, debug=False) is None
    assert 'owa-piggy not found' in capsys.readouterr().err


def test_setup_auth_returns_graph_audience(monkeypatch):
    _patch_owa_piggy(monkeypatch, _ok_run)
    access, base = auth_mod.setup_auth({}, debug=False)
    assert access == 'fake-access-token-for-tests'
    assert base == 'https://graph.microsoft.com/v1.0'


def test_setup_auth_raises_when_broker_missing(monkeypatch):
    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: None)
    with pytest.raises(AuthExpiredError) as exc:
        auth_mod.setup_auth({'owa_piggy_profile': 'work'}, debug=False)
    assert exc.value.exit_code == ExitCode.AUTH_EXPIRED
