"""CLI integration: webcal source dispatch via named profiles.

Verifies the unified resolver routes `events` to the iCal reader
when `--profile X` matches a local webcal profile, and short-circuits
write commands before any auth or HTTP is touched.
"""
import json
import sys
from pathlib import Path

from owa_cal.cli import main


FIXTURE = Path(__file__).parent / 'fixtures' / 'sample.ics'


def _stub_fetch(monkeypatch):
    """Patch fetch_ics so the CLI reads the on-disk fixture instead of
    making a network call. Returns the URL the CLI would have requested."""
    seen = {}
    from owa_cal import ics as ics_mod

    def fake_fetch(url):
        seen['url'] = url
        return FIXTURE.read_text()

    monkeypatch.setattr(ics_mod, 'fetch_ics', fake_fetch)
    return seen


def _trap_setup_auth(monkeypatch):
    """Make any accidental fall-through into Outlook REST loud."""
    from owa_cal import auth as auth_mod

    def explode(*a, **kw):
        raise AssertionError(
            'setup_auth was reached on a webcal-configured run; '
            'dispatcher should have short-circuited.'
        )

    monkeypatch.setattr(auth_mod, 'setup_auth', explode)


def _save_local(alias, url):
    from owa_cal import profiles as profiles_mod
    profiles_mod.add_local(alias, url)


def test_named_profile_routes_to_webcal(
    tmp_config, tmp_profiles, stub_piggy_aliases, clean_env,
    monkeypatch, capsys, force_tz,
):
    force_tz('UTC')
    _save_local('brkh', 'webcal://example.invalid/feed')
    seen = _stub_fetch(monkeypatch)
    _trap_setup_auth(monkeypatch)

    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', '--profile', 'brkh', 'events',
        '--from', '2026-01-01', '--to', '2026-12-31',
    ])
    rc = main()
    out = capsys.readouterr()
    assert rc == 0
    assert seen['url'] == 'webcal://example.invalid/feed'
    payload = json.loads(out.out)
    assert len(payload) == 4
    assert any(e.get('body') for e in payload)


def test_env_var_used_when_no_profile_set(
    tmp_config, tmp_profiles, stub_piggy_aliases, clean_env,
    monkeypatch, capsys, force_tz,
):
    """OWA_CAL_WEBCAL_URL is the unnamed escape hatch: only kicks in
    when no --profile is set and no config pin matches a local profile."""
    force_tz('UTC')
    monkeypatch.setenv('OWA_CAL_WEBCAL_URL', 'https://env.invalid/feed')
    seen = _stub_fetch(monkeypatch)
    _trap_setup_auth(monkeypatch)

    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', 'events', '--from', '2026-01-01', '--to', '2026-12-31',
    ])
    assert main() == 0
    assert seen['url'] == 'https://env.invalid/feed'


def test_named_profile_beats_env_var(
    tmp_config, tmp_profiles, stub_piggy_aliases, clean_env,
    monkeypatch, capsys, force_tz,
):
    """A local webcal profile (resolved via --profile) wins over the
    unnamed env var fallback - the explicit name is more specific."""
    force_tz('UTC')
    _save_local('work', 'https://named.invalid/feed')
    monkeypatch.setenv('OWA_CAL_WEBCAL_URL', 'https://env.invalid/feed')
    seen = _stub_fetch(monkeypatch)
    _trap_setup_auth(monkeypatch)

    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', '--profile', 'work', 'events',
    ])
    main()
    assert seen['url'] == 'https://named.invalid/feed'


def test_collision_warns_to_stderr(
    tmp_config, tmp_profiles, stub_piggy_aliases, clean_env,
    monkeypatch, capsys, force_tz,
):
    """When a local webcal profile name also exists as an owa-piggy
    profile, the resolver picks owa-cal (closest wins) but warns."""
    force_tz('UTC')
    _save_local('brkh', 'https://example.invalid/feed')
    stub_piggy_aliases(['brkh', 'work'], 'work')
    _stub_fetch(monkeypatch)
    _trap_setup_auth(monkeypatch)

    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', '--profile', 'brkh', 'events',
    ])
    main()
    err = capsys.readouterr().err
    assert "'brkh' is also an owa-piggy profile" in err
    assert "owa-cal's webcal source" in err


def test_no_collision_no_warning(
    tmp_config, tmp_profiles, stub_piggy_aliases, clean_env,
    monkeypatch, capsys,
):
    _save_local('brkh', 'https://example.invalid/feed')
    stub_piggy_aliases(['work'])
    _stub_fetch(monkeypatch)
    _trap_setup_auth(monkeypatch)

    monkeypatch.setattr(sys, 'argv', ['owa-cal', '--profile', 'brkh', 'events'])
    main()
    err = capsys.readouterr().err
    assert 'also an owa-piggy profile' not in err


def test_unknown_profile_falls_through_to_oauth(
    tmp_config, tmp_profiles, stub_piggy_aliases, clean_env,
    monkeypatch,
):
    """If --profile X is not a local webcal profile, the resolver
    forwards to owa-piggy with that alias. We assert by trapping
    setup_auth and checking the config that reaches it."""
    from owa_cal import auth as auth_mod
    seen = {}

    class _Stop(Exception):
        pass

    def fake_setup_auth(config, debug=False):
        seen['cfg'] = dict(config)
        raise _Stop()

    monkeypatch.setattr(auth_mod, 'setup_auth', fake_setup_auth)
    monkeypatch.setattr(sys, 'argv', ['owa-cal', '--profile', 'work', 'events'])
    try:
        main()
    except _Stop:
        pass
    assert seen['cfg'].get('owa_piggy_profile') == 'work'


def test_create_rejected_on_webcal_profile(
    tmp_config, tmp_profiles, stub_piggy_aliases, clean_env,
    monkeypatch, capsys,
):
    _save_local('brkh', 'https://example.invalid/feed')
    _trap_setup_auth(monkeypatch)
    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', '--profile', 'brkh', 'create', '--subject', 'X',
    ])
    rc = main()
    err = capsys.readouterr().err
    assert rc == 2
    assert 'read-only feed' in err


def test_update_rejected_on_webcal_profile(
    tmp_config, tmp_profiles, stub_piggy_aliases, clean_env,
    monkeypatch,
):
    _save_local('brkh', 'https://example.invalid/feed')
    _trap_setup_auth(monkeypatch)
    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', '--profile', 'brkh', 'update', '--id', 'X',
    ])
    assert main() == 2


def test_delete_rejected_on_webcal_profile(
    tmp_config, tmp_profiles, stub_piggy_aliases, clean_env,
    monkeypatch,
):
    _save_local('brkh', 'https://example.invalid/feed')
    _trap_setup_auth(monkeypatch)
    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', '--profile', 'brkh', 'delete', '--id', 'X',
    ])
    assert main() == 2


def test_categories_rejected_on_webcal_profile(
    tmp_config, tmp_profiles, stub_piggy_aliases, clean_env,
    monkeypatch,
):
    _save_local('brkh', 'https://example.invalid/feed')
    _trap_setup_auth(monkeypatch)
    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', '--profile', 'brkh', 'categories',
    ])
    assert main() == 2


def test_pretty_renders_body_when_present(
    tmp_config, tmp_profiles, stub_piggy_aliases, clean_env,
    monkeypatch, capsys, force_tz,
):
    force_tz('UTC')
    _save_local('brkh', 'https://example.invalid/feed')
    _stub_fetch(monkeypatch)
    _trap_setup_auth(monkeypatch)
    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', '--profile', 'brkh', 'events',
        '--from', '2026-02-10', '--to', '2026-02-10', '--pretty',
    ])
    main()
    out = capsys.readouterr().out
    assert 'Internal council meeting' in out
    assert 'Agenda item 1' in out
