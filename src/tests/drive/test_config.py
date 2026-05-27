"""owa-drive config file I/O. No network, no real config path."""
from owa_drive import config as config_mod


def test_load_config_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', tmp_path / 'owa-drive' / 'config')
    assert config_mod.load_config() == {}


def test_config_set_and_load_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', tmp_path / 'owa-drive' / 'config')
    config_mod.config_set('owa_piggy_profile', 'work')
    assert config_mod.load_config()['owa_piggy_profile'] == 'work'


def test_save_config_writes_owner_only_perms(tmp_path, monkeypatch):
    path = tmp_path / 'owa-drive' / 'config'
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', path)
    config_mod.save_config({'owa_piggy_profile': 'work'})
    # Secret-bearing config files are written 0600.
    assert (path.stat().st_mode & 0o777) == 0o600


def test_parse_kv_stream_filters_to_allowlist():
    parsed = config_mod.parse_kv_stream('owa_piggy_profile="work"\nbogus="x"\n')
    assert parsed.get('owa_piggy_profile') == 'work'
    assert 'bogus' not in parsed
