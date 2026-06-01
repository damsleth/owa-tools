"""Schema / help / version / validation tests for owa-sites dispatch."""

import json

import pytest

from owa_sites import cli


def test_schema_exit_zero():
    assert cli._main(['schema']) == 0


def test_schema_lists_all_commands(capsys):
    cli._main(['schema'])
    payload = json.loads(capsys.readouterr().out)
    assert payload['tool'] == 'owa-sites'
    assert payload['suite'] == 'owa-tools'
    names = {c['name'] for c in payload['commands']}
    assert {'site', 'lists', 'items', 'files', 'search', 'config', 'refresh'} <= names


def test_version(capsys):
    assert cli._main(['--version']) == 0
    assert capsys.readouterr().out.startswith('owa-sites ')


def test_help_documents_machine_surface(capsys):
    assert cli._main(['help']) == 0
    out = capsys.readouterr().out
    assert 'Machine surface (uniform across the owa suite)' in out
    for token in ('schema', '--agent', '--err-json', '--doctor'):
        assert token in out


def test_unknown_command_raises_usage():
    with pytest.raises(cli.UsageError, match='Unknown command'):
        cli._main(['frobnicate'])


@pytest.mark.parametrize('argv,pattern', [
    (['items'], '--list is required'),
    (['files'], '--path is required'),
    (['search'], '--q is required'),
])
def test_required_flags_validate_before_auth(monkeypatch, argv, pattern):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, 'setup_auth',
        lambda *a, **k: pytest.fail('auth reached before arg validation'),
    )
    with pytest.raises(cli.UsageError, match=pattern):
        cli._main(argv)


def test_subcommand_help_short_circuits(capsys):
    assert cli._main(['lists', '--help']) == 0
    assert 'owa-sites lists' in capsys.readouterr().out
