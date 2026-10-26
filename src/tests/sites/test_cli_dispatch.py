"""End-to-end `_main` dispatch + global-flag tests for owa-sites."""

import json

import pytest

from owa_core.errors import UsageError
from owa_sites import cli


@pytest.fixture
def stub_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, 'setup_auth', lambda config, debug=False: ('tok', 'https://h.test')
    )


def test_main_routes_site(monkeypatch, capsys, stub_auth):
    monkeypatch.setattr(cli.api_mod, 'sp_get', lambda base, ep, tok, **k: {'Title': 'T', 'Url': 'u'})
    assert cli._main(['site', 'owa-casa']) == 0
    assert json.loads(capsys.readouterr().out)['title'] == 'T'


def test_main_routes_lists(monkeypatch, capsys, stub_auth):
    monkeypatch.setattr(cli.api_mod, 'paginate_sp', lambda base, ep, tok, **k: [])
    assert cli._main(['lists', '--site', 'owa-casa']) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_main_routes_items(monkeypatch, capsys, stub_auth):
    monkeypatch.setattr(cli.api_mod, 'paginate_sp', lambda base, ep, tok, **k: [])
    assert cli._main(['items', '--site', 'owa-casa', '--list', 'Documents']) == 0
    capsys.readouterr()


def test_main_routes_files(monkeypatch, capsys, stub_auth):
    monkeypatch.setattr(cli.api_mod, 'paginate_sp', lambda base, ep, tok, **k: [])
    assert cli._main(['files', '--site', 'owa-casa', '--path', '/x']) == 0
    capsys.readouterr()


def test_main_routes_search(monkeypatch, capsys, stub_auth):
    monkeypatch.setattr(cli.api_mod, 'sp_get', lambda base, ep, tok, **k: {})
    assert cli._main(['search', '--q', 'budget']) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_main_debug_and_profile_flags(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, 'setup_auth',
        lambda config, debug=False: seen.update(config=dict(config), debug=debug)
        or ('tok', 'https://h.test'),
    )
    monkeypatch.setattr(cli.api_mod, 'sp_get', lambda base, ep, tok, **k: {'Title': 'T'})
    assert cli._main(['--debug', '--profile', 'work', 'site', 'owa-casa']) == 0
    assert seen['debug'] is True
    assert seen['config']['owa_piggy_profile'] == 'work'
    capsys.readouterr()


def test_main_profile_requires_value():
    with pytest.raises(cli.UsageError, match='--profile requires a value'):
        cli._main(['--profile'])


def test_config_via_main_rejects_profile_subflag(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.config_mod, 'config_set', lambda k, v: saved.__setitem__(k, v))
    with pytest.raises(UsageError, match='Unknown flag: --profile'):
        cli._main(['config', '--profile', 'work'])
    assert saved == {}
    capsys.readouterr()


def test_main_no_args_prints_help(capsys):
    assert cli._main([]) == 0
    assert 'owa-sites' in capsys.readouterr().out


def test_main_function_wraps_dispatch(capsys):
    assert cli.main(['schema']) == 0
    assert json.loads(capsys.readouterr().out)['tool'] == 'owa-sites'
