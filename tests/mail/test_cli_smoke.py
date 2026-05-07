"""CLI smoke tests: help output, unknown command, no-auth routes.

No real network calls and no real tokens.
"""
import os
import subprocess
import sys


def _run(args, env=None):
    cmd = [sys.executable, '-m', 'owa_mail', *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def _safe_path():
    return os.environ.get('PATH', '/usr/bin:/bin')


def test_no_args_shows_help():
    r = _run([])
    assert r.returncode == 0
    assert 'Usage: owa-mail' in r.stdout


def test_help_flag():
    r = _run(['--help'])
    assert r.returncode == 0
    assert 'Usage: owa-mail' in r.stdout


def test_help_subcommand():
    r = _run(['help'])
    assert r.returncode == 0
    assert 'Usage: owa-mail' in r.stdout


def test_unknown_command_exits_nonzero():
    r = _run(['frobnicate'])
    assert r.returncode != 0
    assert 'Unknown command' in r.stderr


def test_config_subcommand_no_flags_runs_without_auth(tmp_path):
    env = {
        'HOME': str(tmp_path),
        'PATH': _safe_path(),
        'XDG_CONFIG_HOME': str(tmp_path / '.config'),
    }
    r = _run(['config'], env=env)
    assert r.returncode == 0
    assert 'Config file:' in r.stderr


def test_messages_without_owa_piggy_fails_with_clear_error(tmp_path):
    """A PATH that doesn't expose `owa-piggy` must yield a clear
    install hint, not a traceback."""
    env = {
        'HOME': str(tmp_path),
        'PATH': str(tmp_path / 'empty-bin') + ':/usr/bin:/bin',
        'XDG_CONFIG_HOME': str(tmp_path / '.config'),
    }
    (tmp_path / 'empty-bin').mkdir()
    r = _run(['messages'], env=env)
    assert r.returncode != 0
    assert 'owa-piggy not found' in r.stderr.lower() or 'token refresh failed' in r.stderr.lower()
    assert 'Traceback' not in r.stderr


def test_subprocess_inherits_env_for_uvx_one_liner(monkeypatch, clean_env):
    """The single-line uvx invocation depends on subprocess.run NOT
    overriding env=, so OWA_REFRESH_TOKEN / OWA_TENANT_ID inherit from
    the parent shell straight through to owa-piggy."""
    from owa_mail import auth as auth_mod

    captured = {}

    class FakeProc:
        returncode = 1
        stdout = ''
        stderr = ''

    def fake_run(argv, *args, **kwargs):
        captured['kwargs'] = kwargs
        return FakeProc()

    monkeypatch.setattr(auth_mod, '_owa_piggy_available', lambda: True)
    monkeypatch.setattr(auth_mod.subprocess, 'run', fake_run)
    auth_mod._refresh_via_owa_piggy({}, debug=False)

    assert 'env' not in captured['kwargs']


def test_profile_flag_forwards_to_owa_piggy(monkeypatch, clean_env):
    """`owa-mail --profile work messages` must invoke
    `owa-piggy token --audience outlook --json --profile work`."""
    from owa_mail import auth as auth_mod

    captured = {}

    class FakeProc:
        returncode = 1
        stdout = ''
        stderr = 'fake error'

    def fake_run(argv, *args, **kwargs):
        captured['argv'] = argv
        return FakeProc()

    monkeypatch.setattr(auth_mod, '_owa_piggy_available', lambda: True)
    monkeypatch.setattr(auth_mod.subprocess, 'run', fake_run)

    result = auth_mod._refresh_via_owa_piggy(
        {'owa_piggy_profile': 'work'}, debug=False
    )
    assert result is None
    assert captured['argv'] == ['owa-piggy', 'token', '--audience', 'outlook', '--json', '--profile', 'work']


def test_refresh_via_owa_piggy_no_profile(monkeypatch, clean_env):
    from owa_mail import auth as auth_mod

    captured = {}

    class FakeProc:
        returncode = 1
        stdout = ''
        stderr = ''

    def fake_run(argv, *args, **kwargs):
        captured['argv'] = argv
        return FakeProc()

    monkeypatch.setattr(auth_mod, '_owa_piggy_available', lambda: True)
    monkeypatch.setattr(auth_mod.subprocess, 'run', fake_run)
    auth_mod._refresh_via_owa_piggy({}, debug=False)
    assert captured['argv'] == ['owa-piggy', 'token', '--audience', 'outlook', '--json']


def test_config_profile_writes_to_file(tmp_config, clean_env):
    from owa_mail.cli import cmd_config
    cmd_config(['--profile', 'work'], {})
    assert tmp_config.exists()
    content = tmp_config.read_text()
    assert 'owa_piggy_profile="work"' in content


def test_config_profile_with_leading_debug_writes_to_file(tmp_config, clean_env, monkeypatch):
    from owa_mail.cli import main

    monkeypatch.setattr(sys, 'argv', ['owa-mail', '--debug', 'config', '--profile', 'work'])

    assert main() == 0
    assert tmp_config.exists()
    assert 'owa_piggy_profile="work"' in tmp_config.read_text()


def _capture_setup_auth_config(monkeypatch, argv):
    """Run main() with sys.argv = argv and capture the config dict that
    setup_auth receives."""
    from owa_mail import auth as auth_mod
    from owa_mail.cli import main

    seen = {}

    class _Stop(Exception):
        pass

    def fake_setup_auth(config, debug=False):
        seen['config'] = dict(config)
        raise _Stop()

    monkeypatch.setattr(sys, 'argv', argv)
    monkeypatch.setattr(auth_mod, 'setup_auth', fake_setup_auth)
    try:
        main()
    except _Stop:
        pass
    return seen.get('config', {})


def test_global_profile_flag_overrides_for_subcommand(tmp_config, clean_env, monkeypatch):
    seen = _capture_setup_auth_config(
        monkeypatch, ['owa-mail', '--profile', 'work', 'messages']
    )
    assert seen.get('owa_piggy_profile') == 'work'


def test_profile_flag_after_subcommand_also_works(tmp_config, clean_env, monkeypatch):
    seen = _capture_setup_auth_config(
        monkeypatch, ['owa-mail', 'messages', '--profile', 'home']
    )
    assert seen.get('owa_piggy_profile') == 'home'


def test_global_profile_overrides_config_pin(tmp_config, clean_env, monkeypatch):
    from owa_mail import config as config_mod
    config_mod.config_set('owa_piggy_profile', 'pinned')
    seen = _capture_setup_auth_config(
        monkeypatch, ['owa-mail', '--profile', 'override', 'messages']
    )
    assert seen.get('owa_piggy_profile') == 'override'
