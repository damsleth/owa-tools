"""Black-box subprocess smoke tests for the owa-vids CLI surface."""
import json
import subprocess
import sys


def _run(*args, env=None):
    return subprocess.run(
        [sys.executable, '-m', 'owa_vids', *args],
        capture_output=True, text=True, env=env,
    )


def _broker_missing_env(tmp_path):
    empty_bin = tmp_path / 'empty-bin'
    empty_bin.mkdir()
    return {'HOME': str(tmp_path), 'PATH': str(empty_bin)}


def test_no_args_shows_help():
    result = _run()
    assert result.returncode == 0
    assert 'owa-vids' in result.stdout


def test_help_flag():
    result = _run('--help')
    assert result.returncode == 0
    assert 'Traceback' not in result.stderr


def test_version_flag():
    result = _run('--version')
    assert result.returncode == 0
    assert result.stdout.startswith('owa-vids ')


def test_schema_subcommand():
    result = _run('schema')
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload['tool'] == 'owa-vids'
    assert {c['name'] for c in payload['commands']} == {'info', 'get', 'check', 'config'}


def test_unknown_command_exits_2(tmp_path):
    result = _run('frobnicate', env=_broker_missing_env(tmp_path))
    assert result.returncode == 2
    assert 'Traceback' not in result.stderr


def test_get_without_source_exits_2(tmp_path):
    result = _run('get', env=_broker_missing_env(tmp_path))
    assert result.returncode == 2
    assert 'owa-piggy' not in result.stderr.lower()


def test_aliases_resolve_to_canonical_help():
    for alias, canonical in (('show', 'info'), ('download', 'get'), ('probe', 'check')):
        result = _run(alias, '--help')
        assert result.returncode == 0
        assert f'owa-vids {canonical}' in result.stdout
