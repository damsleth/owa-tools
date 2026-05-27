"""owa-sched config I/O and work-day window resolution. No network.

The work-window tests pin the fix that made `availability` honour the
configured `default_work_start`/`default_work_end` (it previously
hard-coded 08:00-17:00 while `find-time` already respected config).
"""
from owa_sched import cli
from owa_sched import config as config_mod

# ----- config file I/O -----

def test_load_config_seeds_work_window_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', tmp_path / 'owa-sched' / 'config')
    config = config_mod.load_config()
    assert config['default_work_start'] == '08:00'
    assert config['default_work_end'] == '17:00'
    assert config['default_timezone'] == config_mod.DEFAULT_TIMEZONE


def test_config_set_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', tmp_path / 'owa-sched' / 'config')
    config_mod.config_set('default_work_start', '07:30')
    config_mod.config_set('owa_piggy_profile', 'work')
    loaded = config_mod.load_config()
    assert loaded['default_work_start'] == '07:30'
    assert loaded['owa_piggy_profile'] == 'work'


# ----- work-window resolution in availability -----

def _stub_schedule(monkeypatch, seen):
    def fake_get_schedule(who, from_, to_, start_hhmm, end_hhmm, interval, tz,
                          token, base, debug=False):
        seen.update(start=start_hhmm, end=end_hhmm)
        return []

    monkeypatch.setattr(cli, '_call_get_schedule', fake_get_schedule)


def test_availability_uses_configured_work_window(monkeypatch):
    seen = {}
    _stub_schedule(monkeypatch, seen)
    cli.cmd_availability(
        ['--who', 'a@example.com', '--date', '2026-05-12'],
        {'default_work_start': '07:30', 'default_work_end': '16:00'},
        'tok', 'https://graph.test',
    )
    assert seen['start'] == '07:30'
    assert seen['end'] == '16:00'


def test_availability_flag_overrides_config(monkeypatch):
    seen = {}
    _stub_schedule(monkeypatch, seen)
    cli.cmd_availability(
        ['--who', 'a@example.com', '--date', '2026-05-12', '--start', '10:00'],
        {'default_work_start': '07:30'},
        'tok', 'https://graph.test',
    )
    assert seen['start'] == '10:00'


def test_availability_falls_back_to_default_window(monkeypatch):
    seen = {}
    _stub_schedule(monkeypatch, seen)
    cli.cmd_availability(
        ['--who', 'a@example.com', '--date', '2026-05-12'],
        {}, 'tok', 'https://graph.test',
    )
    assert seen['start'] == '08:00'
    assert seen['end'] == '17:00'
