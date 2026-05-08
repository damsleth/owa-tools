"""Token acquisition via the shared owa-piggy broker contract."""
import json

import pytest

from owa_core import auth as core_auth
from owa_core.errors import ExitCode
from owa_graph import auth as auth_mod


class FakeProc:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_owa_piggy(monkeypatch, fake_run, available=True):
    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: '/usr/bin/owa-piggy' if available else None)
    monkeypatch.setattr(core_auth.subprocess, 'run', fake_run)


def _version_ok():
    return FakeProc(stdout='owa-piggy 0.7.1\n')


def test_resolve_api_base_graph_default():
    assert auth_mod.resolve_api_base('graph') == 'https://graph.microsoft.com/v1.0'


def test_resolve_api_base_graph_beta():
    assert auth_mod.resolve_api_base('graph', beta=True) == 'https://graph.microsoft.com/beta'


def test_resolve_api_base_outlook():
    assert auth_mod.resolve_api_base('outlook') == 'https://outlook.office.com/api/v2.0'


def test_resolve_api_base_unknown_audience_exits(capsys):
    with pytest.raises(SystemExit) as exc:
        auth_mod.resolve_api_base('frobnicate')
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert 'unknown audience' in err
    assert 'graph' in err


def test_resolve_api_base_beta_warns_for_non_graph(capsys):
    base = auth_mod.resolve_api_base('outlook', beta=True)
    assert base == 'https://outlook.office.com/api/v2.0'
    assert '--beta has no effect' in capsys.readouterr().err


def test_refresh_via_owa_piggy_missing_binary(monkeypatch, capsys):
    _patch_owa_piggy(monkeypatch, fake_run=lambda *a, **k: FakeProc(), available=False)
    assert auth_mod._refresh_via_owa_piggy({}) is None
    err = capsys.readouterr().err
    assert 'owa-piggy not found' in err
    assert 'damsleth/tap/owa-piggy' in err


def test_refresh_via_owa_piggy_happy_path_forwards_audience_and_profile(monkeypatch):
    captured = []

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return _version_ok()
        captured.append(argv)
        return FakeProc(stdout=json.dumps({'access_token': 'AT'}))

    _patch_owa_piggy(monkeypatch, fake_run)
    out = auth_mod._refresh_via_owa_piggy({'owa_piggy_profile': 'work'}, audience='graph')
    assert out == 'AT'
    assert captured == [[
        'owa-piggy', 'token', '--audience', 'graph', '--json',
        '--profile', 'work',
    ]]


def test_refresh_via_owa_piggy_no_profile_when_none(monkeypatch):
    captured = []

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return _version_ok()
        captured.append(argv)
        return FakeProc(stdout=json.dumps({'access_token': 'AT'}))

    _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}, audience='outlook') == 'AT'
    assert captured == [['owa-piggy', 'token', '--audience', 'outlook', '--json']]


def test_refresh_via_owa_piggy_old_json_broker_blocks(monkeypatch, capsys):
    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.0\n')
        raise AssertionError('token call should be blocked')

    _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}) is None
    assert 'too old' in capsys.readouterr().err


def test_refresh_via_owa_piggy_unparseable_version_does_not_block(monkeypatch):
    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy something-unparseable\n')
        return FakeProc(stdout=json.dumps({'access_token': 'AT'}))

    _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}) == 'AT'


def test_refresh_via_owa_piggy_oserror_on_subprocess(monkeypatch, capsys):
    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return _version_ok()
        raise OSError('no such file')

    _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}) is None
    assert 'failed to run owa-piggy token' in capsys.readouterr().err


def test_refresh_via_owa_piggy_nonzero_rc_passes_stderr(monkeypatch, capsys):
    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return _version_ok()
        return FakeProc(returncode=1, stderr='ERROR: refresh expired')

    _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}) is None
    assert 'refresh expired' in capsys.readouterr().err


def test_refresh_via_owa_piggy_non_json_output(monkeypatch, capsys):
    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return _version_ok()
        return FakeProc(stdout='not-json')

    _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}) is None
    assert 'non-JSON' in capsys.readouterr().err


def test_refresh_via_owa_piggy_missing_access_token(monkeypatch, capsys):
    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return _version_ok()
        return FakeProc(stdout=json.dumps({}))

    _patch_owa_piggy(monkeypatch, fake_run)
    assert auth_mod._refresh_via_owa_piggy({}) is None
    assert 'access_token' in capsys.readouterr().err


def test_do_token_refresh_uses_graph_broker(monkeypatch):
    monkeypatch.setattr(auth_mod, '_refresh_via_owa_piggy', lambda *a, **k: 'PIGGY_AT')
    assert auth_mod.do_token_refresh({}, audience='graph') == 'PIGGY_AT'


def test_setup_auth_returns_token_and_base(monkeypatch):
    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return _version_ok()
        return FakeProc(stdout=json.dumps({'access_token': 'AT'}))

    _patch_owa_piggy(monkeypatch, fake_run)
    access, base = auth_mod.setup_auth({}, audience='graph', beta=True)
    assert access == 'AT'
    assert base == 'https://graph.microsoft.com/beta'


def test_setup_auth_failure_exits_with_auth_code(monkeypatch):
    _patch_owa_piggy(monkeypatch, fake_run=lambda *a, **k: FakeProc(), available=False)
    with pytest.raises(SystemExit) as exc:
        auth_mod.setup_auth({'owa_piggy_profile': 'work'})
    assert exc.value.code == ExitCode.AUTH_EXPIRED
