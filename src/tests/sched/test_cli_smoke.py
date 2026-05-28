"""CLI smoke tests for owa-sched."""
import subprocess
import sys


def _run(args, env=None):
    cmd = [sys.executable, '-m', 'owa_sched', *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_no_args_shows_help():
    r = _run([])
    assert r.returncode == 0
    assert 'Usage: owa-sched' in r.stdout


def test_help_flag():
    r = _run(['--help'])
    assert r.returncode == 0
    assert 'Usage: owa-sched' in r.stdout


def test_version_flag():
    r = _run(['--version'])
    assert r.returncode == 0
    assert r.stdout.strip().startswith('owa-sched ')


def test_unknown_command_exits_nonzero():
    r = _run(['frobnicate'])
    assert r.returncode != 0
    assert 'Unknown command' in r.stderr


def test_config_subcommand_runs_without_auth(tmp_path):
    env = {
        'HOME': str(tmp_path),
        'PATH': '/usr/bin:/bin',
        'XDG_CONFIG_HOME': str(tmp_path / '.config'),
    }
    r = _run(['config'], env=env)
    assert r.returncode == 0
    assert 'Config file:' in r.stderr


def test_availability_without_owa_piggy_fails_clean(tmp_path):
    env = {
        'HOME': str(tmp_path),
        'PATH': str(tmp_path / 'empty-bin') + ':/usr/bin:/bin',
        'XDG_CONFIG_HOME': str(tmp_path / '.config'),
    }
    (tmp_path / 'empty-bin').mkdir()
    r = _run(['availability', '--who', 'test@x.com'], env=env)
    assert r.returncode != 0
    assert 'owa-piggy not found' in r.stderr.lower() or 'token refresh failed' in r.stderr.lower()
    assert 'Traceback' not in r.stderr


def test_availability_without_who_after_auth_stub(monkeypatch, tmp_config, clean_env):
    """The argument-validation branch must surface a clear error."""
    from owa_sched import auth as auth_mod
    from owa_sched import cli as cli_mod

    monkeypatch.setattr(auth_mod, 'setup_auth',
                        lambda config, debug=False: ('fake', 'http://x'))
    monkeypatch.setattr(sys, 'argv', ['owa-sched', 'availability'])

    rc = cli_mod.main()
    assert rc == 2
