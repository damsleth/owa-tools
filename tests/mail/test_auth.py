"""Tests for the owa-mail auth bridge to owa-piggy."""
import json

import pytest

from owa_core import auth as core_auth
from owa_core.errors import ExitCode


class FakeProc:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_owa_piggy(monkeypatch, fake_run, available=True):
    from owa_mail import auth as auth_mod

    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: '/usr/bin/owa-piggy' if available else None)
    monkeypatch.setattr(core_auth.subprocess, 'run', fake_run)
    return auth_mod


def test_refresh_via_owa_piggy_returns_access_token(monkeypatch, clean_env):
    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(stdout=json.dumps({'access_token': 'fake-access-token-for-tests'}))

    auth_mod = _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}, debug=False) == 'fake-access-token-for-tests'


def test_refresh_via_owa_piggy_non_json_output(monkeypatch, capsys, clean_env):
    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(stdout='not json at all')

    auth_mod = _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}, debug=False) is None
    assert 'non-JSON' in capsys.readouterr().err


def test_refresh_via_owa_piggy_missing_access_token(monkeypatch, clean_env):
    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(stdout=json.dumps({'foo': 'bar'}))

    auth_mod = _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}, debug=False) is None


def test_refresh_via_owa_piggy_not_in_path(monkeypatch, capsys, clean_env):
    auth_mod = _patch_owa_piggy(
        monkeypatch, fake_run=lambda *a, **k: FakeProc(), available=False
    )
    assert auth_mod._refresh_via_owa_piggy({}, debug=False) is None
    err = capsys.readouterr().err
    assert 'owa-piggy not found' in err
    assert 'damsleth/tap/owa-piggy' in err


def test_refresh_via_owa_piggy_subprocess_failure_prints_stderr(
    monkeypatch, capsys, clean_env,
):
    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(returncode=1, stderr='ERROR: profile not found')

    auth_mod = _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}, debug=False) is None
    assert 'profile not found' in capsys.readouterr().err


def test_owa_piggy_version_too_old_blocks_refresh(monkeypatch, capsys, clean_env):
    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(returncode=0, stdout='owa-piggy 0.1.0\n')
        raise AssertionError('token call should be blocked')

    auth_mod = _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}, debug=False) is None
    assert 'too old' in capsys.readouterr().err


def test_owa_piggy_version_unparseable_does_not_block(monkeypatch, clean_env):
    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(returncode=0, stdout='garbage\n')
        return FakeProc(stdout=json.dumps({'access_token': 'fake-access-token-for-tests'}))

    auth_mod = _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}, debug=False) == 'fake-access-token-for-tests'


def test_setup_auth_owa_piggy_failure_exits_with_auth_code(monkeypatch, clean_env):
    from owa_mail import auth as auth_mod

    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: None)
    with pytest.raises(SystemExit) as exc:
        auth_mod.setup_auth({'owa_piggy_profile': 'work'}, debug=False)
    assert exc.value.code == ExitCode.AUTH_EXPIRED


def test_setup_auth_returns_outlook_audience(monkeypatch, clean_env):
    from owa_mail import auth as auth_mod

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(stdout=json.dumps({'access_token': 'fake-access-token-for-tests'}))

    _patch_owa_piggy(monkeypatch, fake_run)
    access, base = auth_mod.setup_auth({}, debug=False)
    assert access == 'fake-access-token-for-tests'
    assert base == 'https://outlook.office.com/api/v2.0'
