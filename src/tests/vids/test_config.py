"""Config I/O and the one-time JSON migration."""
import json

import pytest

from owa_core.errors import UsageError
from owa_vids import config as config_mod


def test_load_config_returns_empty_on_missing_file(tmp_config):
    assert config_mod.load_config() == {}


def test_config_set_persists_region(tmp_config):
    config_mod.config_set('region', 'swon-mediap.svc.ms')
    assert config_mod.load_config() == {'region': 'swon-mediap.svc.ms'}


def test_config_set_rejects_unknown_key(tmp_config):
    with pytest.raises(UsageError):
        config_mod.config_set('bad_key', 'x')


def test_migrate_json_config_imports_old_keys(tmp_config, capsys):
    legacy = tmp_config.parent / 'config.json'
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({'profile': 'swon', 'region': 'swon-mediap.svc.ms'}))

    config = config_mod.load_config()

    assert config == {'owa_piggy_profile': 'swon', 'region': 'swon-mediap.svc.ms'}
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
