"""owa-ado auth + org-base coverage."""
import json

import pytest

from owa_ado import auth
from owa_core import auth as core_auth
from owa_core.errors import AuthExpiredError, ExitCode


class FakeProc:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_org_base_builds_dev_azure_url():
    assert auth.org_base('ACME-Corp') == 'https://dev.azure.com/ACME-Corp'
    assert auth.org_base('/Org/') == 'https://dev.azure.com/Org'


def test_setup_auth_returns_devops_token(monkeypatch):
    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: '/usr/bin/owa-piggy')

    captured = {}

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        captured['argv'] = argv
        return FakeProc(stdout=json.dumps({'access_token': 'devops-access'}))

    monkeypatch.setattr(core_auth.subprocess, 'run', fake_run)
    access = auth.setup_auth({}, debug=False)
    assert access == 'devops-access'
    # The broker must be asked for the devops audience specifically.
    assert '--audience' in captured['argv']
    assert 'devops' in captured['argv']


def test_setup_auth_missing_broker_raises_auth_error(monkeypatch):
    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: None)
    with pytest.raises(AuthExpiredError) as exc:
        auth.setup_auth({}, debug=False)
    assert exc.value.exit_code == ExitCode.AUTH_EXPIRED


def test_do_token_refresh_preserves_legacy_none_contract(monkeypatch):
    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: None)
    assert auth.do_token_refresh({}, debug=False) is None
