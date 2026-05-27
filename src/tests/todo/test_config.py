"""Tests for owa-todo config file I/O."""
import stat

import pytest

from owa_todo.config import config_set, load_config, save_config


def test_load_config_seeds_default_timezone(tmp_config):
    assert not tmp_config.exists()
    cfg = load_config()
    assert cfg.get('default_timezone')
    assert 'owa_piggy_profile' not in cfg


def test_save_and_load_roundtrip(tmp_config):
    save_config({'owa_piggy_profile': 'work', 'default_folder': 'fX'})
    cfg = load_config()
    assert cfg['owa_piggy_profile'] == 'work'
    assert cfg['default_folder'] == 'fX'


def test_save_sets_0600(tmp_config):
    save_config({'owa_piggy_profile': 'work'})
    assert stat.S_IMODE(tmp_config.stat().st_mode) == 0o600


def test_config_set_preserves_other_keys(tmp_config):
    save_config({'owa_piggy_profile': 'work', 'default_folder': 'fX'})
    config_set('default_folder', 'fY')
    cfg = load_config()
    assert cfg['default_folder'] == 'fY'
    assert cfg['owa_piggy_profile'] == 'work'


def test_config_set_rejects_unknown_key(tmp_config):
    with pytest.raises(ValueError):
        config_set('EVIL_KEY', 'pwned')
