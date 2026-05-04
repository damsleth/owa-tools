"""CLI integration: webcal source dispatch.

Verifies the dispatcher routes `events` to the iCal reader and
short-circuits write commands before any auth or HTTP is touched.
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


def test_events_uses_webcal_when_env_var_set(
    tmp_config, clean_env, monkeypatch, capsys, force_tz,
):
    force_tz('UTC')
    monkeypatch.setenv('OWA_CAL_WEBCAL_URL', 'webcal://example.invalid/feed')
    seen = _stub_fetch(monkeypatch)
    _trap_setup_auth(monkeypatch)

    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', 'events', '--from', '2026-01-01', '--to', '2026-12-31',
    ])
    rc = main()
    out = capsys.readouterr()
    assert rc == 0
    assert seen['url'] == 'webcal://example.invalid/feed'
    payload = json.loads(out.out)
    assert len(payload) == 4
    # body field is populated on the webcal path.
    assert any(e.get('body') for e in payload)


def test_events_uses_webcal_when_config_set(
    tmp_config, clean_env, monkeypatch, capsys, force_tz,
):
    force_tz('UTC')
    from owa_cal import config as config_mod
    config_mod.config_set('webcal_url', 'https://example.invalid/feed')
    _stub_fetch(monkeypatch)
    _trap_setup_auth(monkeypatch)

    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', 'events', '--from', '2026-01-01', '--to', '2026-12-31',
    ])
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 4


def test_env_var_overrides_config_webcal(
    tmp_config, clean_env, monkeypatch, capsys,
):
    """OWA_CAL_WEBCAL_URL takes precedence over webcal_url in the
    config file - matches the env-wins-over-config rule established by
    the existing OUTLOOK_* code path."""
    from owa_cal import config as config_mod
    config_mod.config_set('webcal_url', 'https://from-config.invalid/feed')
    monkeypatch.setenv('OWA_CAL_WEBCAL_URL', 'https://from-env.invalid/feed')
    seen = _stub_fetch(monkeypatch)
    _trap_setup_auth(monkeypatch)

    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'events'])
    main()
    assert seen['url'] == 'https://from-env.invalid/feed'


def test_create_rejected_on_webcal_source(
    tmp_config, clean_env, monkeypatch, capsys,
):
    monkeypatch.setenv('OWA_CAL_WEBCAL_URL', 'https://example.invalid/feed')
    _trap_setup_auth(monkeypatch)
    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', 'create', '--subject', 'X',
    ])
    rc = main()
    err = capsys.readouterr().err
    assert rc == 2
    assert 'read-only feed' in err


def test_update_rejected_on_webcal_source(
    tmp_config, clean_env, monkeypatch, capsys,
):
    monkeypatch.setenv('OWA_CAL_WEBCAL_URL', 'https://example.invalid/feed')
    _trap_setup_auth(monkeypatch)
    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'update', '--id', 'X'])
    assert main() == 2


def test_delete_rejected_on_webcal_source(
    tmp_config, clean_env, monkeypatch, capsys,
):
    monkeypatch.setenv('OWA_CAL_WEBCAL_URL', 'https://example.invalid/feed')
    _trap_setup_auth(monkeypatch)
    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'delete', '--id', 'X'])
    assert main() == 2


def test_categories_rejected_on_webcal_source(
    tmp_config, clean_env, monkeypatch, capsys,
):
    monkeypatch.setenv('OWA_CAL_WEBCAL_URL', 'https://example.invalid/feed')
    _trap_setup_auth(monkeypatch)
    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'categories'])
    assert main() == 2


def test_config_webcal_writes_to_file(tmp_config, clean_env):
    from owa_cal.cli import cmd_config
    cmd_config(['--webcal', 'https://example.invalid/feed?token=abc'], {})
    assert tmp_config.exists()
    content = tmp_config.read_text()
    assert 'webcal_url="https://example.invalid/feed?token=abc"' in content


def test_config_clear_webcal(tmp_config, clean_env):
    from owa_cal import config as config_mod
    from owa_cal.cli import cmd_config
    config_mod.config_set('webcal_url', 'https://x.invalid/feed')
    cmd_config(['--clear-webcal'], {})
    content = tmp_config.read_text()
    assert 'webcal_url=""' in content


def test_pretty_renders_body_when_present(
    tmp_config, clean_env, monkeypatch, capsys, force_tz,
):
    force_tz('UTC')
    monkeypatch.setenv('OWA_CAL_WEBCAL_URL', 'https://example.invalid/feed')
    _stub_fetch(monkeypatch)
    _trap_setup_auth(monkeypatch)
    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', 'events', '--from', '2026-02-10', '--to', '2026-02-10',
        '--pretty',
    ])
    main()
    out = capsys.readouterr().out
    assert 'Internal council meeting' in out
    assert 'Agenda item 1' in out
