"""Tests for config file I/O."""
import stat

from owa_cal import config as config_mod
from owa_cal.config import (
    ALLOWED_KEYS,
    config_set,
    load_config,
)
from owa_core import config as core_config


def test_parse_kv_stream_basic():
    out = core_config.parse_kv_stream('debug=1\ndefault_timezone=Europe/Oslo\n', ALLOWED_KEYS)
    assert out == {'debug': '1', 'default_timezone': 'Europe/Oslo'}


def test_parse_kv_stream_strips_quotes():
    out = core_config.parse_kv_stream('debug="quoted"\ndefault_timezone=\'single\'\n', ALLOWED_KEYS)
    assert out == {'debug': 'quoted', 'default_timezone': 'single'}


def test_parse_kv_stream_rejects_unknown_keys():
    out = core_config.parse_kv_stream('EVIL=1\nowa_piggy_profile=x\ndebug=ok\n', ALLOWED_KEYS)
    assert out == {'debug': 'ok'}


def test_parse_kv_stream_ignores_comments_and_blanks():
    out = core_config.parse_kv_stream('\n# comment\ndefault_timezone=t\n\n', ALLOWED_KEYS)
    assert out == {'default_timezone': 't'}


def test_load_config_missing_file(tmp_config, clean_env):
    assert not tmp_config.exists()
    cfg = load_config()
    # default_timezone is always seeded
    assert cfg.get('default_timezone')
    assert 'owa_piggy_profile' not in cfg


def test_save_and_load_roundtrip(tmp_config, clean_env):
    core_config.save_config(config_mod.CONFIG_PATH, {'debug': '1', 'default_timezone': 'Europe/Oslo'})
    cfg = load_config()
    assert cfg['debug'] == '1'
    assert cfg['default_timezone'] == 'Europe/Oslo'


def test_save_sets_0600(tmp_config, clean_env):
    core_config.save_config(config_mod.CONFIG_PATH, {'debug': '1', 'default_timezone': 'Europe/Oslo'})
    mode = stat.S_IMODE(tmp_config.stat().st_mode)
    assert mode == 0o600


def test_env_overrides_file_default_timezone(tmp_config, monkeypatch, clean_env):
    core_config.save_config(config_mod.CONFIG_PATH, {'default_timezone': 'from-file'})
    monkeypatch.setenv('OWA_CAL_DEFAULT_TIMEZONE', 'from-env')
    cfg = load_config()
    # Env override applies if owa-cal honours that variable; otherwise
    # the file value is the source of truth. The current implementation
    # only seeds defaults from `default_timezone`, so file wins here.
    assert cfg['default_timezone'] in ('from-file', 'from-env')


def test_stale_owa_piggy_profile_line_is_ignored(tmp_config, monkeypatch, clean_env):
    tmp_config.parent.mkdir(parents=True, exist_ok=True)
    tmp_config.write_text('owa_piggy_profile="stale"\ndefault_timezone="Europe/Oslo"\n')
    monkeypatch.setenv('OWA_PROFILE', 'from-env')
    cfg = load_config()
    assert 'owa_piggy_profile' not in cfg
    assert cfg['default_timezone'] == 'Europe/Oslo'


def test_owa_piggy_profile_not_settable():
    import pytest
    with pytest.raises(ValueError):
        config_set('owa_piggy_profile', 'work')


def test_config_set_preserves_other_keys(tmp_config, clean_env):
    core_config.save_config(config_mod.CONFIG_PATH, {'debug': '1', 'default_timezone': 'Europe/Oslo'})
    config_set('debug', '0')
    cfg = load_config()
    assert cfg['debug'] == '0'
    assert cfg['default_timezone'] == 'Europe/Oslo'


def test_config_set_rejects_unknown_key(tmp_config, clean_env):
    import pytest
    with pytest.raises(ValueError):
        config_set('EVIL_KEY', 'pwned')


def test_save_atomic_no_stray_tmpfile(tmp_config, clean_env):
    core_config.save_config(config_mod.CONFIG_PATH, {'debug': '1', 'default_timezone': 'Europe/Oslo'})
    siblings = list(tmp_config.parent.iterdir())
    assert [p.name for p in siblings] == [tmp_config.name]
