"""CLI smoke tests: help output, unknown command, no-auth routes.

No real network calls and no real tokens. The config-skips-auth path
and the help output must not raise.
"""
import subprocess
import sys


def _run(args, env=None):
    cmd = [sys.executable, '-m', 'owa_cal', *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_no_args_shows_help():
    r = _run([])
    assert r.returncode == 0
    assert 'Usage: owa-cal' in r.stdout


def test_help_flag():
    r = _run(['--help'])
    assert r.returncode == 0
    assert 'Usage: owa-cal' in r.stdout


def test_help_subcommand():
    r = _run(['help'])
    assert r.returncode == 0
    assert 'Usage: owa-cal' in r.stdout


def test_unknown_command_exits_nonzero():
    r = _run(['frobnicate'])
    assert r.returncode != 0
    assert 'Unknown command' in r.stderr


def test_config_subcommand_no_flags_runs_without_auth(tmp_path, monkeypatch):
    """`owa-cal config` (no args) prints the current state and must NOT
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


def test_subprocess_inherits_env_for_uvx_one_liner(monkeypatch, tmp_path, clean_env):
    """The single-line uvx invocation depends on subprocess.run NOT
    overriding env=, so OWA_REFRESH_TOKEN / OWA_TENANT_ID inherit from
    the parent shell straight through to owa-piggy. If a future change
    starts setting env={...} explicitly, this test catches it."""
    from owa_cal import auth as auth_mod

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

    # The contract: no explicit env= means the child inherits the
    # parent's environment, which is what owa-piggy needs to see
    # OWA_REFRESH_TOKEN / OWA_TENANT_ID for env-only mode.
    assert 'env' not in captured['kwargs'], (
        'subprocess.run was called with env={...}; this breaks the uvx '
        'one-liner because owa-piggy will no longer see OWA_REFRESH_TOKEN '
        'and OWA_TENANT_ID from the calling shell.'
    )


def test_profile_flag_forwards_to_owa_piggy(monkeypatch, tmp_path, clean_env):
    """`owa-cal --profile work events` must invoke
    `owa-piggy token --audience outlook --json --profile work`."""
    from owa_cal import auth as auth_mod

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
    from owa_cal import auth as auth_mod

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
    from owa_cal.cli import cmd_config
    cmd_config(['--profile', 'work'], {})
    assert tmp_config.exists()
    content = tmp_config.read_text()
    assert 'owa_piggy_profile="work"' in content


def test_config_profile_with_leading_debug_writes_to_file(tmp_config, clean_env, monkeypatch):
    from owa_cal.cli import main

    monkeypatch.setattr(sys, 'argv', ['owa-cal', '--debug', 'config', '--profile', 'work'])

    assert main() == 0
    assert tmp_config.exists()
    assert 'owa_piggy_profile="work"' in tmp_config.read_text()


def _capture_setup_auth_config(monkeypatch, argv):
    """Run main() with sys.argv = argv and capture the config dict that
    setup_auth receives. Stops execution before any network call by
    raising once setup_auth is reached."""
    from owa_cal import auth as auth_mod
    from owa_cal.cli import main

    seen = {}

    class _Stop(Exception):
        pass

    def fake_setup_auth(config, debug=False):
        seen['config'] = dict(config)
        raise _Stop()

    monkeypatch.setattr(sys, 'argv', argv)
    monkeypatch.setattr(auth_mod, 'setup_auth', fake_setup_auth)
    # cli.py imported setup_auth via `from . import auth as auth_mod`, so
    # patching auth_mod.setup_auth is the load-bearing patch.
    try:
        main()
    except _Stop:
        pass
    return seen.get('config', {})


def test_global_profile_flag_overrides_for_subcommand(tmp_config, clean_env, monkeypatch):
    """`owa-cal --profile work events` must reach setup_auth with the
    profile pinned. This is the multi-tenant entry point."""
    seen = _capture_setup_auth_config(
        monkeypatch, ['owa-cal', '--profile', 'work', 'events']
    )
    assert seen.get('owa_piggy_profile') == 'work'


def test_profile_flag_after_subcommand_also_works(tmp_config, clean_env, monkeypatch):
    """Same outcome whether --profile comes before or after the
    subcommand. Important for muscle memory: `owa-cal events --profile X`
    is at least as natural as `owa-cal --profile X events`."""
    seen = _capture_setup_auth_config(
        monkeypatch, ['owa-cal', 'events', '--profile', 'home']
    )
    assert seen.get('owa_piggy_profile') == 'home'


def test_global_profile_overrides_config_pin(tmp_config, clean_env, monkeypatch):
    """A pinned profile in the config file is overridden by an explicit
    --profile flag at invocation time."""
    from owa_cal import config as config_mod
    config_mod.config_set('owa_piggy_profile', 'pinned')
    seen = _capture_setup_auth_config(
        monkeypatch, ['owa-cal', '--profile', 'override', 'events']
    )
    assert seen.get('owa_piggy_profile') == 'override'


def _safe_path():
    """A minimal PATH so subprocess can find python and nothing else."""
    import os
    return os.environ.get('PATH', '/usr/bin:/bin')
