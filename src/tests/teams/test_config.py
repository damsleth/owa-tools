"""Config round-trip tests for owa-teams. Writes only under tmp_path."""
import pytest

from owa_core import config as core_config
from owa_teams import config as config_mod


def test_load_missing_is_empty(tmp_config):
    assert config_mod.load_config() == {}


def test_config_set_round_trip(tmp_config):
    config_mod.config_set('owa_piggy_profile', 'work')
    config_mod.config_set('teams_region', 'amer')
    loaded = config_mod.load_config()
    assert loaded['owa_piggy_profile'] == 'work'
    assert loaded['teams_region'] == 'amer'


def test_config_set_rejects_unknown_key(tmp_config):
    with pytest.raises(ValueError, match='unknown config key'):
        config_mod.config_set('refresh_token', 'nope')


def test_save_config_round_trip(tmp_config):
    core_config.save_config(config_mod.CONFIG_PATH, {'page_size': '20'})
    assert config_mod.load_config()['page_size'] == '20'
