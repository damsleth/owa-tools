"""CLI smoke tests: help output, unknown command, no-auth routes.

No real network calls and no real tokens. The config-skips-auth path
and the help output must not raise.
"""
import subprocess
import sys


def _run(args, env=None):
    cmd = [sys.executable, '-m', 'cal_cli', *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_no_args_shows_help():
    r = _run([])
    assert r.returncode == 0
    assert 'Usage: cal-cli' in r.stdout


def test_help_flag():
    r = _run(['--help'])
    assert r.returncode == 0
    assert 'Usage: cal-cli' in r.stdout


def test_help_subcommand():
    r = _run(['help'])
    assert r.returncode == 0
    assert 'Usage: cal-cli' in r.stdout


def test_unknown_command_exits_nonzero():
    r = _run(['frobnicate'])
    assert r.returncode != 0
    assert 'Unknown command' in r.stderr


def test_config_subcommand_no_flags_runs_without_auth(tmp_path, monkeypatch):
    """`cal-cli config` (no args) prints the current state and must NOT
    require OUTLOOK_* env or a live token."""
    env = {
        'HOME': str(tmp_path),
        'PATH': _safe_path(),
        'XDG_CONFIG_HOME': str(tmp_path / '.config'),
    }
    r = _run(['config'], env=env)
    assert r.returncode == 0
    assert 'Config file:' in r.stderr


def test_events_without_owa_piggy_fails_with_clear_error(tmp_path):
    """With no OUTLOOK_APP_CLIENT_ID configured we take the owa-piggy
    path. A PATH that doesn't expose `owa-piggy` must yield a clear
    install hint, not a traceback."""
    env = {
        'HOME': str(tmp_path),
        # Deliberately minimal: python is reachable (full inherited PATH
        # is used via _safe_path); but we scrub via a tmp dir so that
        # owa-piggy is not found. To guarantee this we point PATH at an
        # empty dir plus the parent dirs of /usr/bin for core tools.
        'PATH': str(tmp_path / 'empty-bin') + ':/usr/bin:/bin',
        'XDG_CONFIG_HOME': str(tmp_path / '.config'),
    }
    (tmp_path / 'empty-bin').mkdir()
    r = _run(['events'], env=env)
    assert r.returncode != 0
    assert 'owa-piggy not found' in r.stderr.lower() or 'token refresh failed' in r.stderr.lower()
    # Critically: no traceback leaked.
    assert 'Traceback' not in r.stderr


def test_profile_flag_forwards_to_owa_piggy(monkeypatch, tmp_path, clean_env):
    """`cal-cli --profile work events` must invoke
    `owa-piggy --outlook --json --profile work`."""
    from cal_cli import auth as auth_mod

    captured = {}

    class FakeProc:
        returncode = 1
        stdout = ''
        stderr = 'fake error'

    def fake_run(argv, capture_output=False, text=False, check=False):
        captured['argv'] = argv
        return FakeProc()

    monkeypatch.setattr(auth_mod, '_owa_piggy_available', lambda: True)
    monkeypatch.setattr(auth_mod.subprocess, 'run', fake_run)

    result = auth_mod._refresh_via_owa_piggy(
        {'owa_piggy_profile': 'work'}, debug=False
    )
    assert result is None
    assert captured['argv'] == ['owa-piggy', '--outlook', '--json', '--profile', 'work']


def test_refresh_via_owa_piggy_no_profile(monkeypatch, clean_env):
    from cal_cli import auth as auth_mod

    captured = {}

    class FakeProc:
        returncode = 1
        stdout = ''
        stderr = ''

    def fake_run(argv, capture_output=False, text=False, check=False):
        captured['argv'] = argv
        return FakeProc()

    monkeypatch.setattr(auth_mod, '_owa_piggy_available', lambda: True)
    monkeypatch.setattr(auth_mod.subprocess, 'run', fake_run)
    auth_mod._refresh_via_owa_piggy({}, debug=False)
    assert captured['argv'] == ['owa-piggy', '--outlook', '--json']


def test_config_profile_writes_to_file(tmp_config, clean_env):
    from cal_cli.cli import cmd_config
    cmd_config(['--profile', 'work'], {})
    assert tmp_config.exists()
    content = tmp_config.read_text()
    assert 'owa_piggy_profile="work"' in content


def _safe_path():
    """A minimal PATH so subprocess can find python and nothing else."""
    import os
    return os.environ.get('PATH', '/usr/bin:/bin')
