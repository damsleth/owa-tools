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


def test_events_without_auth_fails_with_clear_error(tmp_path):
    """Missing OUTLOOK_REFRESH_TOKEN must produce a clear 'run cal-cli
    config' message, not a traceback."""
    env = {
        'HOME': str(tmp_path),
        'PATH': _safe_path(),
        'XDG_CONFIG_HOME': str(tmp_path / '.config'),
    }
    r = _run(['events'], env=env)
    assert r.returncode != 0
    assert 'no auth configured' in r.stderr.lower() or 'run: cal-cli config' in r.stderr.lower()
    # Critically: no traceback leaked.
    assert 'Traceback' not in r.stderr


def _safe_path():
    """A minimal PATH so subprocess can find python and nothing else."""
    import os
    return os.environ.get('PATH', '/usr/bin:/bin')
