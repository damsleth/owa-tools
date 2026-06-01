"""Schema / help / version / validation tests for owa-planner dispatch."""

import json

import pytest

from owa_planner import cli


def test_schema_exit_zero():
    assert cli._main(['schema']) == 0


def test_schema_lists_all_commands(capsys):
    cli._main(['schema'])
    payload = json.loads(capsys.readouterr().out)
    assert payload['tool'] == 'owa-planner'
    assert payload['suite'] == 'owa-tools'
    names = {c['name'] for c in payload['commands']}
    assert {'plans', 'buckets', 'tasks', 'task', 'config', 'refresh'} <= names


def test_schema_one_command(capsys):
    assert cli._main(['schema', 'tasks']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [c['name'] for c in payload['commands']] == ['tasks']


def test_version(capsys):
    assert cli._main(['--version']) == 0
    assert capsys.readouterr().out.startswith('owa-planner ')


def test_help_documents_machine_surface(capsys):
    assert cli._main(['help']) == 0
    out = capsys.readouterr().out
    assert 'Machine surface (uniform across the owa suite)' in out
    for token in ('schema', '--agent', '--err-json', '--doctor'):
        assert token in out


def test_unknown_command_raises_usage():
    with pytest.raises(cli.UsageError, match='Unknown command'):
        cli._main(['frobnicate'])


def test_task_missing_id_validates_before_auth(monkeypatch):
    # precheck_required_args must raise (exit 2) before setup_auth is reached.
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, 'setup_auth',
        lambda *a, **k: pytest.fail('auth reached before arg validation'),
    )
    with pytest.raises(cli.UsageError, match='--id is required'):
        cli._main(['task'])


def test_unknown_flag_validates_before_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, 'setup_auth',
        lambda *a, **k: pytest.fail('auth reached before arg validation'),
    )
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli._main(['plans', '--bogus'])


def test_subcommand_help_short_circuits(capsys):
    assert cli._main(['tasks', '--help']) == 0
    assert 'owa-planner tasks' in capsys.readouterr().out
