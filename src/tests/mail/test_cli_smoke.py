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
    from owa_core import auth as core_auth
    from owa_mail import auth as auth_mod

    captured = {}

    class FakeProc:
        returncode = 1
        stdout = ''
        stderr = ''

    def fake_run(argv, *args, **kwargs):
        captured['kwargs'] = kwargs
        if argv == ['owa-piggy', '--version']:
            proc = FakeProc()
            proc.returncode = 0
            proc.stdout = 'owa-piggy 0.7.1\n'
            return proc
        return FakeProc()

    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: '/usr/bin/owa-piggy')
    monkeypatch.setattr(core_auth.subprocess, 'run', fake_run)
    auth_mod.do_token_refresh({}, debug=False)

    assert 'env' not in captured['kwargs']


def test_profile_flag_forwards_to_owa_piggy(monkeypatch, clean_env):
    """`owa-mail --profile work messages` must invoke
    `owa-piggy token --audience outlook --json --profile work`."""
    from owa_core import auth as core_auth
    from owa_mail import auth as auth_mod

    captured = {}

    class FakeProc:
        returncode = 1
        stdout = ''
        stderr = 'fake error'

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            proc = FakeProc()
            proc.returncode = 0
            proc.stdout = 'owa-piggy 0.7.1\n'
            return proc
        captured['argv'] = argv
        return FakeProc()

    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: '/usr/bin/owa-piggy')
    monkeypatch.setattr(core_auth.subprocess, 'run', fake_run)

    result = auth_mod.do_token_refresh(
        {'owa_piggy_profile': 'work'}, debug=False
    )
    assert result is None
    assert captured['argv'] == ['owa-piggy', 'token', '--audience', 'outlook', '--json', '--profile', 'work']


def test_do_token_refresh_no_profile(monkeypatch, clean_env):
    from owa_core import auth as core_auth
    from owa_mail import auth as auth_mod

    captured = {}

    class FakeProc:
        returncode = 1
        stdout = ''
        stderr = ''

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            proc = FakeProc()
            proc.returncode = 0
            proc.stdout = 'owa-piggy 0.7.1\n'
            return proc
        captured['argv'] = argv
        return FakeProc()

    monkeypatch.setattr(core_auth.shutil, 'which', lambda name: '/usr/bin/owa-piggy')
    monkeypatch.setattr(core_auth.subprocess, 'run', fake_run)
    auth_mod.do_token_refresh({}, debug=False)
    assert captured['argv'] == ['owa-piggy', 'token', '--audience', 'outlook', '--json']


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


def test_global_profile_ignores_stale_config_line(tmp_config, clean_env, monkeypatch):
    tmp_config.parent.mkdir(parents=True, exist_ok=True)
    tmp_config.write_text('owa_piggy_profile="stale"\n')
    seen = _capture_setup_auth_config(
        monkeypatch, ['owa-mail', '--profile', 'override', 'messages']
    )
    assert seen.get('owa_piggy_profile') == 'override'
