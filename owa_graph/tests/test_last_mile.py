"""Coverage tail: debug branches in auth.py, save_config exception path,
empty-list fallbacks in format.py, the no-flags branch in emit._join_continuation.
"""
import base64
import json
import time

import pytest

from owa_graph import auth as auth_mod
from owa_graph import config as config_mod
from owa_graph import emit
from owa_graph import format as format_mod


# ---------------------------------------------------------------------------
# auth: debug-on branches and result-None paths
# ---------------------------------------------------------------------------

def _make_token(seconds_left):
    payload = {'exp': int(time.time()) + seconds_left}
    seg = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b'=').decode()
    return f'h.{seg}.s'


def test_log_token_remaining_emits_when_debug(capsys):
    auth_mod._log_token_remaining(_make_token(900), debug=True)
    err = capsys.readouterr().err
    assert 'token exchange ok' in err


def test_log_token_remaining_silent_when_remaining_none(capsys):
    # Garbage token -> token_minutes_remaining returns None -> no print.
    auth_mod._log_token_remaining('not.a.token', debug=True)
    assert capsys.readouterr().err == ''


@pytest.fixture
def _reset_version_cache():
    auth_mod._owa_piggy_version_checked = False
    yield
    auth_mod._owa_piggy_version_checked = False


def test_refresh_via_app_reg_debug_logs(monkeypatch, capsys):
    monkeypatch.setattr(
        auth_mod, 'refresh_via_app_registration',
        lambda *a, **k: {'access_token': _make_token(600)},
    )
    config = {
        'GRAPH_REFRESH_TOKEN': 'rt',
        'GRAPH_TENANT_ID': 'tid',
        'GRAPH_APP_CLIENT_ID': 'cid-debug',
    }
    out = auth_mod._refresh_via_app_registration(config, debug=True)
    assert out is not None
    err = capsys.readouterr().err
    assert 'auth via app registration (cid-debug)' in err
    assert 'token exchange ok' in err


def test_refresh_via_app_reg_returns_none_when_no_access_token(monkeypatch):
    monkeypatch.setattr(
        auth_mod, 'refresh_via_app_registration',
        lambda *a, **k: {'refresh_token': 'rt2'},  # no access_token
    )
    config = {
        'GRAPH_REFRESH_TOKEN': 'rt',
        'GRAPH_TENANT_ID': 'tid',
        'GRAPH_APP_CLIENT_ID': 'cid',
    }
    assert auth_mod._refresh_via_app_registration(config) is None


def test_refresh_via_owa_piggy_debug_logs_argv(monkeypatch, capsys, _reset_version_cache):
    monkeypatch.setattr(auth_mod.shutil, 'which', lambda _: '/usr/bin/owa-piggy')
    monkeypatch.setattr(auth_mod, '_check_owa_piggy_version', lambda: True)
    class _Proc:
        returncode = 0
        stdout = json.dumps({'access_token': _make_token(600)})
        stderr = ''
    monkeypatch.setattr(auth_mod.subprocess, 'run', lambda *a, **k: _Proc())
    auth_mod._refresh_via_owa_piggy({}, audience='graph', debug=True)
    err = capsys.readouterr().err
    assert 'auth via owa-piggy' in err
    assert '--audience graph --json' in err


# ---------------------------------------------------------------------------
# config: save_config rolls back temp file on failure
# ---------------------------------------------------------------------------

def test_save_config_unlinks_tmp_on_replace_failure(monkeypatch, tmp_path):
    target = tmp_path / 'owa-graph' / 'config'
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', target)

    def _boom(*a, **k):
        raise OSError('disk full')
    monkeypatch.setattr(config_mod.os, 'replace', _boom)

    with pytest.raises(OSError, match='disk full'):
        config_mod.save_config({'owa_piggy_profile': 'work'})

    # No leftover temp files in the target dir.
    leftovers = [p for p in target.parent.iterdir() if p.name.startswith('.config.')]
    assert leftovers == []


def test_save_config_swallows_unlink_failure_in_cleanup(monkeypatch, tmp_path):
    target = tmp_path / 'owa-graph' / 'config'
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', target)

    def _boom(*a, **k):
        raise OSError('disk full')
    monkeypatch.setattr(config_mod.os, 'replace', _boom)

    # Pre-empt: make Path.unlink raise FileNotFoundError to exercise that
    # branch in the except handler.
    real_unlink = config_mod.Path.unlink
    def _missing(self, *a, **k):
        raise FileNotFoundError(str(self))
    monkeypatch.setattr(config_mod.Path, 'unlink', _missing)
    try:
        with pytest.raises(OSError, match='disk full'):
            config_mod.save_config({'owa_piggy_profile': 'work'})
    finally:
        monkeypatch.setattr(config_mod.Path, 'unlink', real_unlink)


# ---------------------------------------------------------------------------
# format: empty rows fallbacks (unreachable from format_pretty's `if items:`
# guard, but worth pinning so the helpers don't crash if reused).
# ---------------------------------------------------------------------------

def test_format_users_empty_returns_placeholder():
    assert format_mod._format_users([]) == '(no items)'


def test_format_messages_empty_returns_placeholder():
    assert format_mod._format_messages([]) == '(no items)'


def test_format_drive_items_empty_returns_placeholder():
    assert format_mod._format_drive_items([]) == '(no items)'


# ---------------------------------------------------------------------------
# emit: long argv with no flag tokens hits the single-chunk branch
# ---------------------------------------------------------------------------

def test_join_continuation_no_flags_returns_single_line():
    parts = ['echo', 'one', 'two', 'three', 'four', 'five']
    out = emit._join_continuation(parts)
    assert out == 'echo one two three four five'
    assert '\n' not in out
