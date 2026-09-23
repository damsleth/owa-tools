"""Config I/O."""
import pytest

from owa_core.errors import UsageError
from owa_vids import config as config_mod


def test_load_config_returns_empty_on_missing_file(tmp_config):
    assert config_mod.load_config() == {}


def test_config_set_persists_regions(tmp_config):
    config_mod.config_set('regions', '{"default":"globex-mediap.svc.ms"}')
    assert config_mod.load_config() == {'regions': '{"default":"globex-mediap.svc.ms"}'}


def test_config_set_rejects_unknown_key(tmp_config):
    with pytest.raises(UsageError):
        config_mod.config_set('bad_key', 'x')


def test_set_region_is_per_profile(tmp_config):
    config_mod.set_region({'owa_piggy_profile': 'globex'}, 'globex-mediap.svc.ms')
    # a later invocation reloads from disk before caching another profile
    cfg = config_mod.load_config()
    cfg['owa_piggy_profile'] = 'acme'
    config_mod.set_region(cfg, 'acme-mediap.svc.ms')

    final = config_mod.load_config()
    assert config_mod.get_region({**final, 'owa_piggy_profile': 'globex'}) == 'globex-mediap.svc.ms'
    assert config_mod.get_region({**final, 'owa_piggy_profile': 'acme'}) == 'acme-mediap.svc.ms'


def test_set_region_uses_default_bucket_without_profile(tmp_config):
    config_mod.set_region({}, 'def-mediap.svc.ms')
    assert config_mod.get_region(config_mod.load_config()) == 'def-mediap.svc.ms'
