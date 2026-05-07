"""CLI-level tests: argv parsing, --curl/--az exit-before-HTTP,
body resolution. We monkeypatch setup_auth so no real owa-piggy or
network is touched."""
import json
import sys

import pytest

from owa_graph import cli


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch):
    """Every test in this module gets a fake token + base URL."""
    def _fake(_config, audience='graph', beta=False, debug=False):
        if audience != 'graph':
            from owa_graph import auth
            return 'tok', auth.AUDIENCE_API_BASE[audience]
        base = 'https://graph.microsoft.com/beta' if beta else 'https://graph.microsoft.com/v1.0'
        return 'tok', base
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', _fake)
    monkeypatch.setattr(
        cli.config_mod, 'load_config', lambda: {'default_audience': 'graph'},
    )


def _run(monkeypatch, *args):
    monkeypatch.setattr(sys, 'argv', ['owa-graph', *args])
    return cli.main()


def test_help_no_args(monkeypatch, capsys):
    rc = _run(monkeypatch)
    out = capsys.readouterr().out
    assert rc == 0
    assert 'Usage: owa-graph' in out


def test_help_explicit(monkeypatch, capsys):
    assert _run(monkeypatch, 'help') == 0
    out = capsys.readouterr().out
    assert 'METHOD: GET' in out


def test_unknown_verb_errors(monkeypatch, capsys):
    rc = _run(monkeypatch, 'FROBNICATE', '/me')
    err = capsys.readouterr().err
    assert rc == 1
    assert 'Unknown command' in err


def test_get_without_path_errors(monkeypatch, capsys):
    rc = _run(monkeypatch, 'GET')
    err = capsys.readouterr().err
    assert rc == 1
    assert 'requires a path' in err


def test_curl_renders_and_exits(monkeypatch, capsys):
    rc = _run(monkeypatch, 'GET', '/me', '--curl')
    out = capsys.readouterr().out
    assert rc == 0
    assert 'curl' in out
    assert 'Bearer tok' in out
    assert 'graph.microsoft.com/v1.0/me' in out


def test_az_renders_and_exits(monkeypatch, capsys):
    rc = _run(monkeypatch, 'GET', '/me', '--az')
    out = capsys.readouterr().out
    assert rc == 0
    assert 'az rest' in out
    assert 'Authorization=Bearer tok' in out


def test_beta_changes_base(monkeypatch, capsys):
    _run(monkeypatch, 'GET', '/me', '--beta', '--curl')
    out = capsys.readouterr().out
    assert 'graph.microsoft.com/beta/me' in out


def test_audience_changes_base(monkeypatch, capsys):
    _run(monkeypatch, 'GET', 'me/events', '--audience', 'outlook', '--curl')
    out = capsys.readouterr().out
    assert 'outlook.office.com/api/v2.0/me/events' in out


def test_select_top_filter_shortcuts(monkeypatch, capsys):
    _run(
        monkeypatch, 'GET', '/users',
        '--top', '5',
        '--select', 'id,displayName',
        '--filter', "startswith(displayName,'A')",
        '--curl',
    )
    out = capsys.readouterr().out
    assert '$top=5' in out
    assert '$select=id%2CdisplayName' in out
    assert 'startswith' in out


def test_extra_header_passthrough(monkeypatch, capsys):
    _run(
        monkeypatch, 'GET', '/me/messages',
        '--header', 'Prefer=odata.maxpagesize=10',
        '--curl',
    )
    out = capsys.readouterr().out
    assert 'Prefer: odata.maxpagesize=10' in out


def test_body_literal_json(monkeypatch, capsys):
    _run(
        monkeypatch, 'PATCH', '/me/messages/x',
        '--body', '{"isRead":true}',
        '--curl',
    )
    out = capsys.readouterr().out
    assert '--data' in out
    assert 'isRead' in out


def test_body_file_ref_kept_as_at_path(monkeypatch, capsys):
    _run(
        monkeypatch, 'POST', '/me/sendMail',
        '--body', '@/tmp/mail.json',
        '--curl',
    )
    out = capsys.readouterr().out
    assert '/tmp/mail.json' in out


def test_body_stdin(monkeypatch, capsys):
    import io
    monkeypatch.setattr('sys.stdin', io.StringIO('{"a":1}'))
    _run(
        monkeypatch, 'POST', '/me/sendMail',
        '--body', '-',
        '--curl',
    )
    out = capsys.readouterr().out
    assert "'a':" in out or '"a":' in out


def test_invalid_body_json_exits(monkeypatch, capsys):
    with pytest.raises(SystemExit):
        _run(monkeypatch, 'POST', '/x', '--body', 'not-json', '--curl')


def test_unknown_flag_returns_error(monkeypatch, capsys):
    rc = _run(monkeypatch, 'GET', '/me', '--bogus')
    err = capsys.readouterr().err
    assert rc == 1
    assert 'Unknown flag' in err


def test_method_case_insensitive(monkeypatch, capsys):
    rc = _run(monkeypatch, 'get', '/me', '--curl')
    out = capsys.readouterr().out
    assert rc == 0
    assert '-X GET' in out


def test_global_profile_forwarded_to_config(monkeypatch, capsys):
    """--profile before the verb populates owa_piggy_profile in config
    that setup_auth sees."""
    seen = {}
    def _capture(config, audience='graph', beta=False, debug=False):
        seen['profile'] = config.get('owa_piggy_profile')
        return 'tok', 'https://graph.microsoft.com/v1.0'
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', _capture)
    _run(monkeypatch, '--profile', 'work', 'GET', '/me', '--curl')
    assert seen['profile'] == 'work'
