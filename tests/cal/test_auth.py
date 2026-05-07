"""Tests for the auth bridge to owa-piggy.

These do NOT exercise the network. They patch subprocess.run and the
PATH probe so the bridge surface (argv shape, version floor, JSON
contract, error messages) is locked in without needing a live
owa-piggy on disk.
"""
import json

import pytest


class FakeProc:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_owa_piggy(monkeypatch, fake_run, available=True):
    from owa_cal import auth as auth_mod
    monkeypatch.setattr(auth_mod, '_owa_piggy_available', lambda: available)
    monkeypatch.setattr(auth_mod, '_owa_piggy_version_checked', True, raising=False)
    monkeypatch.setattr(auth_mod.subprocess, 'run', fake_run)
    return auth_mod


def test_refresh_via_owa_piggy_returns_access_token(monkeypatch, clean_env):
    body = json.dumps({'access_token': 'fake-access-token-for-tests'})

    def fake_run(argv, *args, **kwargs):
        return FakeProc(returncode=0, stdout=body)

    auth_mod = _patch_owa_piggy(monkeypatch, fake_run)
    out = auth_mod._refresh_via_owa_piggy({}, debug=False)
    assert out == 'fake-access-token-for-tests'


def test_refresh_via_owa_piggy_non_json_output(monkeypatch, capsys, clean_env):
    def fake_run(argv, *args, **kwargs):
        return FakeProc(returncode=0, stdout='not json at all')

    auth_mod = _patch_owa_piggy(monkeypatch, fake_run)
    out = auth_mod._refresh_via_owa_piggy({}, debug=False)
    assert out is None
    assert 'non-JSON' in capsys.readouterr().err


def test_refresh_via_owa_piggy_missing_access_token(monkeypatch, clean_env):
    def fake_run(argv, *args, **kwargs):
        return FakeProc(returncode=0, stdout=json.dumps({'foo': 'bar'}))

    auth_mod = _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}, debug=False) is None


def test_refresh_via_owa_piggy_not_in_path(monkeypatch, capsys, clean_env):
    auth_mod = _patch_owa_piggy(
        monkeypatch, fake_run=lambda *a, **k: FakeProc(), available=False
    )
    out = auth_mod._refresh_via_owa_piggy({}, debug=False)
    assert out is None
    err = capsys.readouterr().err
    assert 'owa-piggy not found' in err
    assert 'damsleth/tap/owa-piggy' in err


def test_refresh_via_owa_piggy_subprocess_failure_prints_stderr(
    monkeypatch, capsys, clean_env,
):
    def fake_run(argv, *args, **kwargs):
        return FakeProc(returncode=1, stderr='ERROR: profile not found')

    auth_mod = _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}, debug=False) is None
    assert 'profile not found' in capsys.readouterr().err


def test_owa_piggy_version_too_old_blocks_refresh(monkeypatch, capsys, clean_env):
    """If owa-piggy on PATH is older than the floor we surface a clear
    upgrade hint and refuse to call it. This is the contract that lets
    owa-cal evolve the bridge surface without hidden breakage."""
    from owa_cal import auth as auth_mod

    monkeypatch.setattr(auth_mod, '_owa_piggy_available', lambda: True)
    monkeypatch.setattr(auth_mod, '_owa_piggy_version_checked', False, raising=False)

    calls = {'n': 0}

    def fake_run(argv, *args, **kwargs):
        calls['n'] += 1
        if argv[:2] == ['owa-piggy', '--version']:
            # Pretend an ancient owa-piggy is on PATH.
            return FakeProc(returncode=0, stdout='owa-piggy 0.1.0\n')
        # token call must NOT happen if version is too old
        raise AssertionError('token call should be blocked')

    monkeypatch.setattr(auth_mod.subprocess, 'run', fake_run)
    out = auth_mod._refresh_via_owa_piggy({}, debug=False)
    assert out is None
    err = capsys.readouterr().err
    assert 'too old' in err
    assert calls['n'] == 1


def test_owa_piggy_version_unparseable_does_not_block(monkeypatch, clean_env):
    """If --version output is in an unexpected shape, we don't fail
    closed - the JSON-shape check downstream still catches real
    breakage. Locks the 'be liberal in what you accept' policy in."""
    from owa_cal import auth as auth_mod

    monkeypatch.setattr(auth_mod, '_owa_piggy_available', lambda: True)
    monkeypatch.setattr(auth_mod, '_owa_piggy_version_checked', False, raising=False)

    def fake_run(argv, *args, **kwargs):
        if argv[:2] == ['owa-piggy', '--version']:
            return FakeProc(returncode=0, stdout='garbage\n')
        return FakeProc(
            returncode=0,
            stdout=json.dumps({'access_token': 'fake-access-token-for-tests'}),
        )

    monkeypatch.setattr(auth_mod.subprocess, 'run', fake_run)
    assert auth_mod._refresh_via_owa_piggy({}, debug=False) == 'fake-access-token-for-tests'


def test_setup_auth_app_path_requires_refresh_token_and_tenant(
    monkeypatch, capsys, clean_env,
):
    from owa_cal import auth as auth_mod

    config = {'OUTLOOK_APP_CLIENT_ID': 'cid'}
    with pytest.raises(SystemExit) as exc:
        auth_mod.setup_auth(config, debug=False)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert 'OUTLOOK_REFRESH_TOKEN' in err
    assert 'OUTLOOK_TENANT_ID' in err


def test_setup_auth_owa_piggy_failure_includes_profile_hint(
    monkeypatch, capsys, clean_env,
):
    from owa_cal import auth as auth_mod

    monkeypatch.setattr(auth_mod, 'do_token_refresh', lambda c, debug=False: None)
    with pytest.raises(SystemExit):
        auth_mod.setup_auth({'owa_piggy_profile': 'work'}, debug=False)
    err = capsys.readouterr().err
    assert 'owa-piggy setup --profile work' in err
