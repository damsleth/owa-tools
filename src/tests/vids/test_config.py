"""Config I/O and the one-time JSON migration."""
import json

import pytest

from owa_core.errors import UsageError
from owa_vids import config as config_mod


def test_load_config_returns_empty_on_missing_file(tmp_config):
    assert config_mod.load_config() == {}


def test_config_set_persists_region(tmp_config):
    config_mod.config_set('region', 'globex-mediap.svc.ms')
    assert config_mod.load_config() == {'region': 'globex-mediap.svc.ms'}


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


def test_get_region_falls_back_to_legacy_key(tmp_config):
    # an existing single-tenant config (pre per-profile) still resolves
    assert config_mod.get_region({'region': 'old-mediap.svc.ms'}) == 'old-mediap.svc.ms'


def test_set_region_uses_default_bucket_without_profile(tmp_config):
    config_mod.set_region({}, 'def-mediap.svc.ms')
    assert config_mod.get_region(config_mod.load_config()) == 'def-mediap.svc.ms'


def test_migrate_json_config_imports_old_keys(tmp_config, capsys):
    legacy = tmp_config.parent / 'config.json'
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({'profile': 'globex', 'region': 'globex-mediap.svc.ms'}))

    config = config_mod.load_config()

    assert config == {'owa_piggy_profile': 'globex', 'region': 'globex-mediap.svc.ms'}
    assert not legacy.exists()
    assert tmp_config.exists()
    assert 'migrated' in capsys.readouterr().err


def test_migrate_skips_when_suite_config_exists(tmp_config):
    tmp_config.parent.mkdir(parents=True)
    tmp_config.write_text('region="kept"\n')
    legacy = tmp_config.parent / 'config.json'
    legacy.write_text(json.dumps({'region': 'overwritten'}))

    assert config_mod.load_config() == {'region': 'kept'}
    assert legacy.exists()  # untouched


def test_migrate_tolerates_malformed_json(tmp_config):
    legacy = tmp_config.parent / 'config.json'
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{not json')

    assert config_mod.load_config() == {}
    assert legacy.exists()  # left in place, tool keeps working
