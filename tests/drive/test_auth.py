"""owa-drive auth migration coverage."""
import json

import pytest

from owa_core import auth as core_auth
from owa_core.errors import ExitCode
from owa_drive import auth


class FakeProc:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_setup_auth_returns_graph_api_base(monkeypatch):
    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: '/usr/bin/owa-piggy')

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(stdout=json.dumps({'access_token': 'fake-access-token-for-tests'}))

    monkeypatch.setattr(core_auth.subprocess, 'run', fake_run)
    access, base = auth.setup_auth({}, debug=False)
    assert access == 'fake-access-token-for-tests'
    assert base == 'https://graph.microsoft.com/v1.0'


def test_setup_auth_missing_broker_exits_with_auth_code(monkeypatch):
    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: None)
    with pytest.raises(SystemExit) as exc:
        auth.setup_auth({}, debug=False)
    assert exc.value.code == ExitCode.AUTH_EXPIRED


def test_do_token_refresh_preserves_legacy_none_contract(monkeypatch):
    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: None)
    assert auth.do_token_refresh({}, debug=False) is None
