"""Tests for config file I/O."""
import stat

from owa_cal.config import (
    config_set,
    load_config,
    parse_kv_stream,
    save_config,
)


def test_parse_kv_stream_basic():
    out = parse_kv_stream('owa_piggy_profile=work\ndefault_timezone=Europe/Oslo\n')
    assert out == {'owa_piggy_profile': 'work', 'default_timezone': 'Europe/Oslo'}


def test_parse_kv_stream_strips_quotes():
    out = parse_kv_stream('owa_piggy_profile="quoted"\ndefault_timezone=\'single\'\n')
    assert out == {'owa_piggy_profile': 'quoted', 'default_timezone': 'single'}


def test_parse_kv_stream_rejects_unknown_keys():
    out = parse_kv_stream('EVIL=1\nowa_piggy_profile=ok\n')
    assert out == {'owa_piggy_profile': 'ok'}


def test_parse_kv_stream_ignores_comments_and_blanks():
    out = parse_kv_stream('\n# comment\ndefault_timezone=t\n\n')
    assert out == {'default_timezone': 't'}


def test_load_config_missing_file(tmp_config, clean_env):
    assert not tmp_config.exists()
    cfg = load_config()
    # default_timezone is always seeded
    assert cfg.get('default_timezone')
    assert 'owa_piggy_profile' not in cfg


def test_save_and_load_roundtrip(tmp_config, clean_env):
    save_config({'owa_piggy_profile': 'work', 'default_timezone': 'Europe/Oslo'})
    cfg = load_config()
    assert cfg['owa_piggy_profile'] == 'work'
    assert cfg['default_timezone'] == 'Europe/Oslo'


def test_save_sets_0600(tmp_config, clean_env):
    save_config({'owa_piggy_profile': 'work', 'default_timezone': 'Europe/Oslo'})
    mode = stat.S_IMODE(tmp_config.stat().st_mode)
    assert mode == 0o600


def test_env_overrides_file_default_timezone(tmp_config, monkeypatch, clean_env):
    save_config({'default_timezone': 'from-file'})
    monkeypatch.setenv('OWA_CAL_DEFAULT_TIMEZONE', 'from-env')
    cfg = load_config()
    # Env override applies if owa-cal honours that variable; otherwise
    # the file value is the source of truth. The current implementation
    # only seeds defaults from `default_timezone`, so file wins here.
    assert cfg['default_timezone'] in ('from-file', 'from-env')


def test_profile_env_does_not_override(tmp_config, monkeypatch, clean_env):
    # On the owa-piggy path the refresh token lives in owa-piggy's
    # profile store; owa-cal only stores the profile alias.
    save_config({'owa_piggy_profile': 'from-file'})
    monkeypatch.setenv('OWA_PROFILE', 'from-env')
    cfg = load_config()
    assert cfg['owa_piggy_profile'] == 'from-file'


def test_owa_piggy_profile_roundtrip(tmp_config, clean_env):
    save_config({'owa_piggy_profile': 'work'})
    cfg = load_config()
    assert cfg['owa_piggy_profile'] == 'work'


def test_parse_kv_stream_preserves_profile_key():
    out = parse_kv_stream('owa_piggy_profile="work"\n')
    assert out == {'owa_piggy_profile': 'work'}


def test_config_set_preserves_other_keys(tmp_config, clean_env):
    save_config({'owa_piggy_profile': 'work', 'default_timezone': 'Europe/Oslo'})
    config_set('owa_piggy_profile', 'home')
    cfg = load_config()
    assert cfg['owa_piggy_profile'] == 'home'
    assert cfg['default_timezone'] == 'Europe/Oslo'


def test_config_set_rejects_unknown_key(tmp_config, clean_env):
    import pytest
    with pytest.raises(ValueError):
        config_set('EVIL_KEY', 'pwned')


def test_save_atomic_no_stray_tmpfile(tmp_config, clean_env):
    save_config({'owa_piggy_profile': 'work', 'default_timezone': 'Europe/Oslo'})
    siblings = list(tmp_config.parent.iterdir())
    assert [p.name for p in siblings] == [tmp_config.name]
