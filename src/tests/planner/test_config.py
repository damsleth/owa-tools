"""Config file round-trip for owa-planner (no writes outside tmp_path)."""

from owa_planner import config as config_mod


def test_save_and_load_roundtrip(tmp_config):
    config_mod.save_config({'owa_piggy_profile': 'work'})
    assert config_mod.load_config()['owa_piggy_profile'] == 'work'


def test_config_set_appends(tmp_config):
    config_mod.config_set('default_plan', 'pZ')
    loaded = config_mod.load_config()
    assert loaded['default_plan'] == 'pZ'


def test_config_set_rejects_unknown_key(tmp_config):
    import pytest

    with pytest.raises(ValueError, match='unknown config key'):
        config_mod.config_set('totally_unknown', 'x')
