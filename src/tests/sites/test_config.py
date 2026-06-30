"""Config file round-trip for owa-sites (no writes outside tmp_path)."""

import pytest

from owa_sites import config as config_mod


def test_save_and_load_roundtrip(tmp_config):
    config_mod.save_config({'sharepoint_host': 'contoso.sharepoint.com'})
    assert config_mod.load_config()['sharepoint_host'] == 'contoso.sharepoint.com'


def test_config_set_appends(tmp_config):
    config_mod.config_set('default_site', 'owa-casa')
    assert config_mod.load_config()['default_site'] == 'owa-casa'


def test_config_set_rejects_unknown_key(tmp_config):
    with pytest.raises(ValueError, match='unknown config key'):
        config_mod.config_set('totally_unknown', 'x')


def test_config_unset_removes_key(tmp_config):
    config_mod.config_set('default_site', 'owa-casa')
    config_mod.config_set('sharepoint_host', 'contoso.sharepoint.com')
    config_mod.config_unset('default_site')
    loaded = config_mod.load_config()
    assert 'default_site' not in loaded
    assert loaded['sharepoint_host'] == 'contoso.sharepoint.com'


def test_config_unset_missing_file_is_noop(tmp_config):
    config_mod.config_unset('default_site')  # no file yet
    assert config_mod.load_config() == {}


def test_config_unset_rejects_unknown_key(tmp_config):
    with pytest.raises(config_mod.UsageError, match='unknown config key'):
        config_mod.config_unset('totally_unknown')


def test_config_clear(tmp_config):
    config_mod.config_set('default_site', 'owa-casa')
    config_mod.config_clear()
    assert config_mod.load_config() == {}
    config_mod.config_clear()  # idempotent, no error
