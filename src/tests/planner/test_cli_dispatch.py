"""End-to-end `_main` dispatch, global-flag, and edge-path tests."""

import json

import pytest

from owa_planner import cli


@pytest.fixture
def stub_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, 'setup_auth', lambda config, debug=False: ('tok', 'https://graph.test')
    )


def _stub_get(monkeypatch, value):
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda base, ep, tok, **k: value)


def test_main_routes_plans(monkeypatch, capsys, stub_auth):
    _stub_get(monkeypatch, {'value': [{'id': 'p1', 'title': 'T'}]})
    assert cli._main(['plans']) == 0
    assert json.loads(capsys.readouterr().out)[0]['title'] == 'T'


def test_main_routes_buckets(monkeypatch, capsys, stub_auth):
    _stub_get(monkeypatch, {'value': []})
    assert cli._main(['buckets', '--plan', 'p1']) == 0
    capsys.readouterr()


def test_main_routes_tasks(monkeypatch, capsys, stub_auth):
    _stub_get(monkeypatch, {'value': []})
    assert cli._main(['tasks']) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_main_routes_task(monkeypatch, capsys, stub_auth):
    monkeypatch.setattr(
        cli.api_mod, 'api_get',
        lambda base, ep, tok, **k: (
            {'description': ''} if ep.endswith('/details')
            else {'id': 't1', 'title': 'X', 'assignments': {}}
        ),
    )
    assert cli._main(['task', 't1']) == 0
    assert json.loads(capsys.readouterr().out)['id'] == 't1'


def test_main_debug_and_profile_flags(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, 'setup_auth',
        lambda config, debug=False: seen.update(config=dict(config), debug=debug)
        or ('tok', 'https://graph.test'),
    )
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda base, ep, tok, **k: {'value': []})
    assert cli._main(['--debug', '--profile', 'work', 'plans']) == 0
    assert seen['debug'] is True
    assert seen['config']['owa_piggy_profile'] == 'work'
    capsys.readouterr()


def test_main_all_pages(monkeypatch, capsys, stub_auth):
    monkeypatch.setattr(
        cli.api_mod, 'paginate_all', lambda base, ep, tok, **k: [{'id': 'p1', 'title': 'T'}]
    )
    assert cli._main(['plans', '--all']) == 0
    assert json.loads(capsys.readouterr().out)[0]['id'] == 'p1'


def test_main_data_none_returns_one(monkeypatch, capsys, stub_auth):
    _stub_get(monkeypatch, None)
    assert cli._main(['plans']) == 1
    capsys.readouterr()


def test_main_profile_requires_value():
    with pytest.raises(cli.UsageError, match='--profile requires a value'):
        cli._main(['--profile'])


def test_config_via_main_keeps_profile_as_subflag(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.config_mod, 'config_set', lambda k, v: saved.__setitem__(k, v))
    assert cli._main(['config', '--profile', 'work']) == 0
    assert saved == {'owa_piggy_profile': 'work'}
    capsys.readouterr()


def test_main_no_args_prints_help(capsys):
    assert cli._main([]) == 0
    assert 'owa-planner' in capsys.readouterr().out


def test_main_function_wraps_dispatch(capsys):
    # main() routes through run_with_output_modes; schema needs no auth.
    assert cli.main(['schema']) == 0
    assert json.loads(capsys.readouterr().out)['tool'] == 'owa-planner'


def test_refresh_auth_verify_fails(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, 'do_token_refresh', lambda config, debug=False: 'tok')
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: None)
    assert cli.cmd_refresh([], {}) == 1
    assert 'Auth verification failed' in capsys.readouterr().err


def test_config_display_without_profile(monkeypatch, capsys):
    monkeypatch.setattr(cli.config_mod, 'CONFIG_PATH', '/tmp/owa-planner-x')
    assert cli.cmd_config([], {}) == 0
    out = capsys.readouterr().err
    assert '(not set' in out
