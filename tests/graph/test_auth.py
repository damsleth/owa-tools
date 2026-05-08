"""Token acquisition via owa-piggy.

We don't make real network or subprocess calls; subprocess.run is
monkeypatched. The tests guard the contract: audience -> base URL,
version-check semantics, and the various error messages.
"""
import json

import pytest

from owa_graph import auth as auth_mod


@pytest.fixture(autouse=True)
def _reset_version_cache():
    auth_mod._owa_piggy_version_checked = False
    yield
    auth_mod._owa_piggy_version_checked = False


# ---------------------------------------------------------------------------
# resolve_api_base
# ---------------------------------------------------------------------------

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
    assert 'graph' in err  # known list mentioned


def test_resolve_api_base_beta_warns_for_non_graph(capsys):
    base = auth_mod.resolve_api_base('outlook', beta=True)
    assert base == 'https://outlook.office.com/api/v2.0'
    err = capsys.readouterr().err
    assert '--beta has no effect' in err


# ---------------------------------------------------------------------------
# _parse_version + _check_owa_piggy_version
# ---------------------------------------------------------------------------

def test_parse_version_three_digits():
    assert auth_mod._parse_version('0.6.0') == (0, 6, 0)


def test_parse_version_strips_prerelease_suffix():
    assert auth_mod._parse_version('1.2.3-beta') == (1, 2, 3)


def test_parse_version_garbage_returns_none():
    assert auth_mod._parse_version('not a version') is None
    assert auth_mod._parse_version('1.2') is None


def test_check_owa_piggy_version_passes_when_recent(monkeypatch):
    class _Proc:
        returncode = 0
        stdout = 'owa-piggy 0.7.0\n'
        stderr = ''
    monkeypatch.setattr(auth_mod.subprocess, 'run', lambda *a, **k: _Proc())
    assert auth_mod._check_owa_piggy_version() is True


def test_check_owa_piggy_version_fails_when_old(monkeypatch, capsys):
    class _Proc:
        returncode = 0
        stdout = 'owa-piggy 0.5.0\n'
        stderr = ''
    monkeypatch.setattr(auth_mod.subprocess, 'run', lambda *a, **k: _Proc())
    assert auth_mod._check_owa_piggy_version() is False
    err = capsys.readouterr().err
    assert 'too old' in err


def test_check_owa_piggy_version_tolerant_on_unparseable(monkeypatch):
    class _Proc:
        returncode = 0
        stdout = 'owa-piggy something-unparseable\n'
        stderr = ''
    monkeypatch.setattr(auth_mod.subprocess, 'run', lambda *a, **k: _Proc())
    # Don't fail closed on a parse quirk.
    assert auth_mod._check_owa_piggy_version() is True


def test_check_owa_piggy_version_tolerant_on_oserror(monkeypatch):
    def _raise(*a, **k):
        raise OSError('exec failed')
    monkeypatch.setattr(auth_mod.subprocess, 'run', _raise)
    assert auth_mod._check_owa_piggy_version() is True


def test_check_owa_piggy_version_tolerant_on_nonzero_rc(monkeypatch):
    class _Proc:
        returncode = 1
        stdout = ''
        stderr = 'usage: owa-piggy [-h]'
    monkeypatch.setattr(auth_mod.subprocess, 'run', lambda *a, **k: _Proc())
    assert auth_mod._check_owa_piggy_version() is True


def test_check_owa_piggy_version_caches_result(monkeypatch):
    calls = {'n': 0}
    class _Proc:
        returncode = 0
        stdout = 'owa-piggy 0.7.0\n'
        stderr = ''
    def _run(*a, **k):
        calls['n'] += 1
        return _Proc()
    monkeypatch.setattr(auth_mod.subprocess, 'run', _run)
    auth_mod._check_owa_piggy_version()
    auth_mod._check_owa_piggy_version()
    assert calls['n'] == 1


# (app-registration auth path removed - owa-piggy is the only token source)


# ---------------------------------------------------------------------------
# _refresh_via_owa_piggy
# ---------------------------------------------------------------------------

def test__refresh_via_owa_piggy_missing_binary(monkeypatch, capsys):
    monkeypatch.setattr(auth_mod.shutil, 'which', lambda _: None)
    assert auth_mod._refresh_via_owa_piggy({}) is None
    assert 'owa-piggy not found' in capsys.readouterr().err


def test__refresh_via_owa_piggy_happy_path(monkeypatch):
    monkeypatch.setattr(auth_mod.shutil, 'which', lambda _: '/usr/bin/owa-piggy')
    monkeypatch.setattr(auth_mod, '_check_owa_piggy_version', lambda: True)

    captured_argv = []
    class _Proc:
        returncode = 0
        stdout = json.dumps({'access_token': 'AT'})
        stderr = ''
    def _run(argv, **k):
        captured_argv.append(argv)
        return _Proc()
    monkeypatch.setattr(auth_mod.subprocess, 'run', _run)

    config = {'owa_piggy_profile': 'work'}
    out = auth_mod._refresh_via_owa_piggy(config, audience='graph')
    assert out == 'AT'
    assert captured_argv[0] == [
        'owa-piggy', 'token', '--audience', 'graph', '--json',
        '--profile', 'work',
    ]


def test__refresh_via_owa_piggy_no_profile_when_none(monkeypatch):
    monkeypatch.setattr(auth_mod.shutil, 'which', lambda _: '/usr/bin/owa-piggy')
    monkeypatch.setattr(auth_mod, '_check_owa_piggy_version', lambda: True)
    captured = []
    class _Proc:
        returncode = 0
        stdout = json.dumps({'access_token': 'AT'})
        stderr = ''
    def _run(argv, **k):
        captured.append(argv)
        return _Proc()
    monkeypatch.setattr(auth_mod.subprocess, 'run', _run)
    auth_mod._refresh_via_owa_piggy({}, audience='outlook')
    assert '--profile' not in captured[0]
    assert '--audience' in captured[0]
    assert 'outlook' in captured[0]


def test__refresh_via_owa_piggy_old_version_blocks(monkeypatch):
    monkeypatch.setattr(auth_mod.shutil, 'which', lambda _: '/usr/bin/owa-piggy')
    monkeypatch.setattr(auth_mod, '_check_owa_piggy_version', lambda: False)
    assert auth_mod._refresh_via_owa_piggy({}) is None


def test__refresh_via_owa_piggy_oserror_on_subprocess(monkeypatch, capsys):
    monkeypatch.setattr(auth_mod.shutil, 'which', lambda _: '/usr/bin/owa-piggy')
    monkeypatch.setattr(auth_mod, '_check_owa_piggy_version', lambda: True)
    def _raise(*a, **k):
        raise OSError('no such file')
    monkeypatch.setattr(auth_mod.subprocess, 'run', _raise)
    assert auth_mod._refresh_via_owa_piggy({}) is None
    assert 'failed to run owa-piggy' in capsys.readouterr().err


def test__refresh_via_owa_piggy_nonzero_rc_passes_stderr(monkeypatch, capsys):
    monkeypatch.setattr(auth_mod.shutil, 'which', lambda _: '/usr/bin/owa-piggy')
    monkeypatch.setattr(auth_mod, '_check_owa_piggy_version', lambda: True)
    class _Proc:
        returncode = 1
        stdout = ''
        stderr = 'ERROR: refresh expired'
    monkeypatch.setattr(auth_mod.subprocess, 'run', lambda *a, **k: _Proc())
    assert auth_mod._refresh_via_owa_piggy({}) is None
    assert 'refresh expired' in capsys.readouterr().err


def test__refresh_via_owa_piggy_non_json_output(monkeypatch, capsys):
    monkeypatch.setattr(auth_mod.shutil, 'which', lambda _: '/usr/bin/owa-piggy')
    monkeypatch.setattr(auth_mod, '_check_owa_piggy_version', lambda: True)
    class _Proc:
        returncode = 0
        stdout = 'not-json'
        stderr = ''
    monkeypatch.setattr(auth_mod.subprocess, 'run', lambda *a, **k: _Proc())
    assert auth_mod._refresh_via_owa_piggy({}) is None
    assert 'non-JSON' in capsys.readouterr().err


def test__refresh_via_owa_piggy_missing_access_token(monkeypatch):
    monkeypatch.setattr(auth_mod.shutil, 'which', lambda _: '/usr/bin/owa-piggy')
    monkeypatch.setattr(auth_mod, '_check_owa_piggy_version', lambda: True)
    class _Proc:
        returncode = 0
        stdout = json.dumps({})
        stderr = ''
    monkeypatch.setattr(auth_mod.subprocess, 'run', lambda *a, **k: _Proc())
    assert auth_mod._refresh_via_owa_piggy({}) is None


# ---------------------------------------------------------------------------
# do_token_refresh dispatch
# ---------------------------------------------------------------------------

def test_do_token_refresh_uses_piggy(monkeypatch):
    monkeypatch.setattr(auth_mod, '_refresh_via_owa_piggy', lambda *a, **k: 'PIGGY_AT')
    out = auth_mod.do_token_refresh({}, audience='graph')
    assert out == 'PIGGY_AT'


# ---------------------------------------------------------------------------
# setup_auth (process-exit boundary)
# ---------------------------------------------------------------------------

def test_setup_auth_returns_token_and_base(monkeypatch):
    monkeypatch.setattr(auth_mod, 'do_token_refresh', lambda *a, **k: 'AT')
    access, base = auth_mod.setup_auth({}, audience='graph', beta=True)
    assert access == 'AT'
    assert base == 'https://graph.microsoft.com/beta'


def test_setup_auth_failure_exits_with_piggy_message(monkeypatch, capsys):
    monkeypatch.setattr(auth_mod, 'do_token_refresh', lambda *a, **k: None)
    with pytest.raises(SystemExit):
        auth_mod.setup_auth({'owa_piggy_profile': 'work'})
    err = capsys.readouterr().err
    assert 'owa-piggy setup' in err
    assert '--profile work' in err
