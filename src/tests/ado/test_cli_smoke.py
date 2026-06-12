"""CLI smoke tests for owa-ado."""
import subprocess
import sys


def _run(args, env=None, input_=None):
    cmd = [sys.executable, '-m', 'owa_ado', *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, input=input_)


def test_no_args_shows_help():
    r = _run([])
    assert r.returncode == 0
    assert 'Usage: owa-ado' in r.stdout


def test_help_flag():
    r = _run(['--help'])
    assert r.returncode == 0
    assert 'Usage: owa-ado' in r.stdout


def test_version_flag():
    r = _run(['--version'])
    assert r.returncode == 0
    assert r.stdout.strip().startswith('owa-ado ')


def test_unknown_command_exits_nonzero():
    r = _run(['frobnicate'])
    assert r.returncode != 0
    assert 'Unknown command' in r.stderr


def test_schema_emits_json():
    r = _run(['schema'])
    assert r.returncode == 0
    assert '"tool"' in r.stdout and 'owa-ado' in r.stdout


def test_config_subcommand_runs_without_auth(tmp_path):
    env = {
        'HOME': str(tmp_path),
        'PATH': '/usr/bin:/bin',
        'XDG_CONFIG_HOME': str(tmp_path / '.config'),
    }
    r = _run(['config'], env=env)
    assert r.returncode == 0
    assert 'Config file:' in r.stderr


def test_projects_without_org_is_usage_error(tmp_path):
    env = {
        'HOME': str(tmp_path),
        'PATH': '/usr/bin:/bin',
        'XDG_CONFIG_HOME': str(tmp_path / '.config'),
    }
    r = _run(['projects'], env=env)
    assert r.returncode == 2
    assert 'organisation' in r.stderr.lower()


def test_wi_without_project_is_usage_error(tmp_path):
    env = {
        'HOME': str(tmp_path),
        'PATH': '/usr/bin:/bin',
        'XDG_CONFIG_HOME': str(tmp_path / '.config'),
        'OWA_ADO_ORG': 'SomeOrg',
    }
    r = _run(['wi'], env=env)
    assert r.returncode == 2
    assert 'project' in r.stderr.lower()


def test_missing_broker_fails_clean(tmp_path):
    env = {
        'HOME': str(tmp_path),
        'PATH': str(tmp_path / 'empty-bin') + ':/usr/bin:/bin',
        'XDG_CONFIG_HOME': str(tmp_path / '.config'),
        'OWA_ADO_ORG': 'SomeOrg',
    }
    (tmp_path / 'empty-bin').mkdir()
    r = _run(['projects'], env=env)
    assert r.returncode != 0
    assert 'owa-piggy not found' in r.stderr.lower()
    assert 'Traceback' not in r.stderr
