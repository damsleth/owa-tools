"""Coverage for CLI paths beyond the curl/az happy path:

- Real (mocked) HTTP execution: pretty/raw/json output
- cmd_refresh and cmd_config
- error branches: --header missing =, --query missing =, missing flag values
- _read_file_body and @file body resolution
- global-flag handling: missing --profile value, debug flag wiring
"""
import io
import json
import sys

import pytest

from owa_graph import cli


# ---------------------------------------------------------------------------
# Shared stubs: bypass setup_auth and api_request so tests focus on cli logic.
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_auth(monkeypatch):
    monkeypatch.setattr(
        cli.auth_mod, 'setup_auth',
        lambda _c, audience='graph', beta=False, debug=False:
        ('tok', 'https://graph.microsoft.com/v1.0'),
    )


@pytest.fixture
def loaded_config(monkeypatch):
    """Default load_config stub - tests can override per-test."""
    monkeypatch.setattr(
        cli.config_mod, 'load_config',
        lambda: {'default_audience': 'graph'},
    )


def _run(monkeypatch, *args):
    monkeypatch.setattr(sys, 'argv', ['owa-graph', *args])
    return cli.main()


# ---------------------------------------------------------------------------
# Real-execution path (api.api_request mocked)
# ---------------------------------------------------------------------------

def test_get_executes_and_prints_compact_json(monkeypatch, stub_auth, loaded_config, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'api_request',
        lambda *a, **k: {'displayName': 'kim', 'mail': 'k@x.com'},
    )
    rc = _run(monkeypatch, 'GET', '/me')
    out = capsys.readouterr().out
    assert rc == 0
    # Compact JSON (no indentation) on stdout.
    assert '"displayName": "kim"' in out
    assert '\n  "' not in out


def test_get_pretty_uses_format_pretty(monkeypatch, stub_auth, loaded_config, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'api_request',
        lambda *a, **k: {'value': [
            {'displayName': 'A', 'userPrincipalName': 'a@x.com', 'id': 'x'},
        ]},
    )
    rc = _run(monkeypatch, 'GET', '/users', '--pretty')
    out = capsys.readouterr().out
    assert rc == 0
    # Table form, not raw JSON.
    assert 'a@x.com' in out
    assert '"value"' not in out


def test_get_returns_1_on_api_failure(monkeypatch, stub_auth, loaded_config):
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: None)
    rc = _run(monkeypatch, 'GET', '/missing')
    assert rc == 1


def test_get_raw_writes_bytes_to_stdout_buffer(monkeypatch, stub_auth, loaded_config, capsysbinary):
    """Use capsysbinary so non-UTF-8 bytes don't poison the capture stream."""
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: b'\x89PNG\r\n\x1a\n')
    rc = _run(monkeypatch, 'GET', '/me/photo/$value', '--raw')
    out = capsysbinary.readouterr().out
    assert rc == 0
    assert b'\x89PNG' in out


def test_post_with_file_body_reads_file(monkeypatch, stub_auth, loaded_config, tmp_path, capsys):
    body_file = tmp_path / 'body.json'
    body_file.write_text('{"subject":"hi"}')
    seen = {}
    def _capture(method, base, endpoint, token, body=None, **k):
        seen['body'] = body
        return {'ok': True}
    monkeypatch.setattr(cli.api_mod, 'api_request', _capture)
    rc = _run(monkeypatch, 'POST', '/me/messages', '--body', f'@{body_file}')
    assert rc == 0
    assert seen['body'] == b'{"subject":"hi"}'


def test_post_file_body_missing_exits(monkeypatch, stub_auth, loaded_config, tmp_path, capsys):
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: {'ok': True})
    with pytest.raises(SystemExit):
        _run(monkeypatch, 'POST', '/me/messages', '--body', f'@{tmp_path}/nonexistent')
    err = capsys.readouterr().err
    assert 'cannot read body file' in err


def test_extra_headers_forwarded_to_api(monkeypatch, stub_auth, loaded_config):
    seen = {}
    def _capture(method, base, endpoint, token, body=None, extra_headers=None, **k):
        seen['headers'] = extra_headers
        return {'ok': True}
    monkeypatch.setattr(cli.api_mod, 'api_request', _capture)
    rc = _run(monkeypatch, 'GET', '/me', '--header', 'Prefer=odata.maxpagesize=10')
    assert rc == 0
    assert seen['headers'] == {'Prefer': 'odata.maxpagesize=10'}


def test_query_pair_appended_to_url(monkeypatch, stub_auth, loaded_config):
    seen = {}
    def _capture(method, base, endpoint, token, **k):
        seen['endpoint'] = endpoint
        return {'ok': True}
    monkeypatch.setattr(cli.api_mod, 'api_request', _capture)
    _run(monkeypatch, 'GET', '/me', '--query', 'foo=bar', '--query', 'baz=qux')
    assert 'foo=bar' in seen['endpoint']
    assert 'baz=qux' in seen['endpoint']


# ---------------------------------------------------------------------------
# cmd_refresh
# ---------------------------------------------------------------------------

def test_refresh_graph_audience_probes_me(monkeypatch, loaded_config, capsys):
    monkeypatch.setattr(cli.auth_mod, 'do_token_refresh', lambda *a, **k: 'AT')
    monkeypatch.setattr(
        cli.api_mod, 'api_get',
        lambda base, ep, tok, **k: {'displayName': 'kim'},
    )
    rc = _run(monkeypatch, 'refresh')
    err = capsys.readouterr().err
    assert rc == 0
    assert 'Authenticated as kim' in err


def test_refresh_graph_audience_handles_outlook_displayname(monkeypatch, loaded_config, capsys):
    monkeypatch.setattr(cli.auth_mod, 'do_token_refresh', lambda *a, **k: 'AT')
    # Outlook REST returns 'DisplayName' (PascalCase).
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: {'DisplayName': 'KIM'})
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {'default_audience': 'outlook'})
    rc = _run(monkeypatch, 'refresh')
    assert rc == 0
    assert 'KIM' in capsys.readouterr().err


def test_refresh_non_outlook_audience_skips_me(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, 'do_token_refresh', lambda *a, **k: 'AT')
    called = {'n': 0}
    monkeypatch.setattr(
        cli.api_mod, 'api_get',
        lambda *a, **k: called.update(n=called['n'] + 1) or {},
    )
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {'default_audience': 'azure'})
    rc = _run(monkeypatch, 'refresh')
    err = capsys.readouterr().err
    assert rc == 0
    assert called['n'] == 0
    assert "Token minted for audience 'azure'" in err


def test_refresh_token_failure_returns_1(monkeypatch, loaded_config, capsys):
    monkeypatch.setattr(cli.auth_mod, 'do_token_refresh', lambda *a, **k: None)
    rc = _run(monkeypatch, 'refresh')
    assert rc == 1
    assert 'Token refresh failed' in capsys.readouterr().err


def test_refresh_me_probe_failure_returns_1(monkeypatch, loaded_config, capsys):
    monkeypatch.setattr(cli.auth_mod, 'do_token_refresh', lambda *a, **k: 'AT')
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: None)
    rc = _run(monkeypatch, 'refresh')
    assert rc == 1
    assert 'Auth verification failed' in capsys.readouterr().err


def test_refresh_rejects_extra_args(monkeypatch, loaded_config, capsys):
    rc = _run(monkeypatch, 'refresh', '--bogus')
    assert rc == 1
    assert 'Unknown flag' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cmd_config
# ---------------------------------------------------------------------------

def test_config_no_args_prints_current_state(monkeypatch, loaded_config, capsys):
    rc = _run(monkeypatch, 'config')
    err = capsys.readouterr().err
    assert rc == 0
    assert 'Config file' in err
    assert 'default_audience=graph' in err


def test_config_shows_pinned_profile(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.config_mod, 'load_config',
        lambda: {
            'default_audience': 'graph',
            'owa_piggy_profile': 'work',
            'GRAPH_APP_CLIENT_ID': 'cid-xxx',
        },
    )
    rc = _run(monkeypatch, 'config')
    err = capsys.readouterr().err
    assert rc == 0
    assert 'owa_piggy_profile=work' in err
    assert 'GRAPH_APP_CLIENT_ID=cid-xxx' in err


def test_config_writes_profile(monkeypatch, loaded_config, capsys):
    written = {}
    monkeypatch.setattr(
        cli.config_mod, 'config_set',
        lambda k, v: written.update({k: v}),
    )
    rc = _run(monkeypatch, 'config', '--profile', 'work')
    err = capsys.readouterr().err
    assert rc == 0
    assert written == {'owa_piggy_profile': 'work'}
    assert 'profile saved' in err


def test_config_writes_all_three(monkeypatch, loaded_config, capsys):
    written = {}
    monkeypatch.setattr(
        cli.config_mod, 'config_set',
        lambda k, v: written.update({k: v}),
    )
    rc = _run(
        monkeypatch, 'config',
        '--profile', 'work',
        '--app-client-id', 'cid',
        '--audience', 'outlook',
    )
    assert rc == 0
    assert written == {
        'owa_piggy_profile': 'work',
        'GRAPH_APP_CLIENT_ID': 'cid',
        'default_audience': 'outlook',
    }


def test_config_unknown_flag(monkeypatch, loaded_config, capsys):
    rc = _run(monkeypatch, 'config', '--bogus')
    assert rc == 1
    assert 'Unknown flag' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Error / boundary paths
# ---------------------------------------------------------------------------

def test_header_missing_equals_returns_1(monkeypatch, stub_auth, loaded_config, capsys):
    rc = _run(monkeypatch, 'GET', '/me', '--header', 'noequals')
    assert rc == 1
    assert 'expects K=V' in capsys.readouterr().err


def test_query_missing_equals_returns_1(monkeypatch, stub_auth, loaded_config, capsys):
    rc = _run(monkeypatch, 'GET', '/me', '--query', 'noequals')
    assert rc == 1
    assert 'expects K=V' in capsys.readouterr().err


def test_missing_flag_value_exits(monkeypatch, stub_auth, loaded_config, capsys):
    with pytest.raises(SystemExit):
        _run(monkeypatch, 'GET', '/me', '--top')
    assert '--top requires a value' in capsys.readouterr().err


def test_global_profile_without_value_returns_1(monkeypatch, loaded_config, capsys):
    rc = _run(monkeypatch, '--profile')
    err = capsys.readouterr().err
    assert rc == 1
    assert '--profile requires a value' in err


def test_debug_flag_enables_logging(monkeypatch, loaded_config, capsys):
    seen = {}
    def _capture(_config, audience='graph', beta=False, debug=False):
        seen['debug'] = debug
        return 'tok', 'https://graph.microsoft.com/v1.0'
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', _capture)
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: {'ok': True})
    _run(monkeypatch, '--debug', 'GET', '/me')
    assert seen['debug'] is True
    assert 'verbose logging enabled' in capsys.readouterr().err


def test_graph_debug_env_enables_debug(monkeypatch, loaded_config, capsys):
    monkeypatch.setenv('GRAPH_DEBUG', '1')
    seen = {}
    def _capture(_config, audience='graph', beta=False, debug=False):
        seen['debug'] = debug
        return 'tok', 'https://graph.microsoft.com/v1.0'
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', _capture)
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: {'ok': True})
    _run(monkeypatch, 'GET', '/me')
    assert seen['debug'] is True


def test_help_long_flag(monkeypatch, capsys):
    rc = _run(monkeypatch, '--help')
    assert rc == 0
    assert 'Usage: owa-graph' in capsys.readouterr().out


def test_only_globals_no_command_prints_help(monkeypatch, loaded_config, capsys):
    rc = _run(monkeypatch, '--debug')
    assert rc == 0
    assert 'Usage: owa-graph' in capsys.readouterr().out


def test_help_subcommand_after_globals(monkeypatch, loaded_config, capsys):
    rc = _run(monkeypatch, '--debug', 'help')
    assert rc == 0
    out = capsys.readouterr().out
    assert 'Usage: owa-graph' in out


# ---------------------------------------------------------------------------
# _first_nonglobal helper directly (covers the `i += 2` skip-value path)
# ---------------------------------------------------------------------------

def test_first_nonglobal_skips_profile_value():
    assert cli._first_nonglobal(['--profile', 'work', 'config']) == 'config'


def test_first_nonglobal_skips_debug_flag():
    assert cli._first_nonglobal(['--debug', 'GET', '/me']) == 'GET'


def test_first_nonglobal_returns_empty_when_only_globals():
    assert cli._first_nonglobal(['--debug', '--verbose']) == ''


def test_first_nonglobal_handles_dangling_profile():
    # --profile with no value at end - the i+=2 jumps past len(argv).
    assert cli._first_nonglobal(['--profile']) == ''


# ---------------------------------------------------------------------------
# Body resolution edge cases
# ---------------------------------------------------------------------------

def test_invalid_stdin_body_exits(monkeypatch, stub_auth, loaded_config, capsys):
    monkeypatch.setattr(sys, 'stdin', io.StringIO('definitely not json'))
    with pytest.raises(SystemExit):
        _run(monkeypatch, 'POST', '/me', '--body', '-', '--curl')
    assert 'stdin body is not valid JSON' in capsys.readouterr().err


def test_config_command_keeps_its_own_profile_flag(monkeypatch, loaded_config, capsys):
    """Global --profile is forwarded to owa-piggy normally, BUT under
    `owa-graph config --profile <alias>` it's the subcommand form
    that writes to the config file. Verify the subcommand wins."""
    written = {}
    monkeypatch.setattr(
        cli.config_mod, 'config_set',
        lambda k, v: written.update({k: v}),
    )
    rc = _run(monkeypatch, 'config', '--profile', 'newalias')
    assert rc == 0
    assert written == {'owa_piggy_profile': 'newalias'}
