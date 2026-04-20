"""Tests for config file I/O."""
import stat

from cal_cli.config import (
    config_set,
    load_config,
    parse_kv_stream,
    save_config,
)


def test_parse_kv_stream_basic():
    out = parse_kv_stream('OUTLOOK_REFRESH_TOKEN=abc\nOUTLOOK_TENANT_ID=xyz\n')
    assert out == {'OUTLOOK_REFRESH_TOKEN': 'abc', 'OUTLOOK_TENANT_ID': 'xyz'}


def test_parse_kv_stream_strips_quotes():
    out = parse_kv_stream('OUTLOOK_REFRESH_TOKEN="quoted"\nOUTLOOK_TENANT_ID=\'single\'\n')
    assert out == {'OUTLOOK_REFRESH_TOKEN': 'quoted', 'OUTLOOK_TENANT_ID': 'single'}


def test_parse_kv_stream_rejects_unknown_keys():
    out = parse_kv_stream('EVIL=1\nOUTLOOK_REFRESH_TOKEN=ok\n')
    assert out == {'OUTLOOK_REFRESH_TOKEN': 'ok'}


def test_parse_kv_stream_ignores_comments_and_blanks():
    out = parse_kv_stream('\n# comment\nOUTLOOK_TENANT_ID=t\n\n')
    assert out == {'OUTLOOK_TENANT_ID': 't'}


def test_load_config_missing_file(tmp_config, clean_env):
    assert not tmp_config.exists()
    cfg = load_config()
    # default_timezone is always seeded
    assert cfg.get('default_timezone')
    assert 'OUTLOOK_REFRESH_TOKEN' not in cfg


def test_save_and_load_roundtrip(tmp_config, clean_env):
    save_config({'OUTLOOK_REFRESH_TOKEN': 'fake-rt', 'OUTLOOK_TENANT_ID': 'tid-1'})
    cfg = load_config()
    assert cfg['OUTLOOK_REFRESH_TOKEN'] == 'fake-rt'
    assert cfg['OUTLOOK_TENANT_ID'] == 'tid-1'


def test_save_sets_0600(tmp_config, clean_env):
    save_config({'OUTLOOK_REFRESH_TOKEN': 'x', 'OUTLOOK_TENANT_ID': 'y'})
    mode = stat.S_IMODE(tmp_config.stat().st_mode)
    assert mode == 0o600


def test_env_overrides_file(tmp_config, monkeypatch, clean_env):
    save_config({'OUTLOOK_REFRESH_TOKEN': 'from-file', 'OUTLOOK_TENANT_ID': 'tid'})
    monkeypatch.setenv('OUTLOOK_REFRESH_TOKEN', 'from-env')
    cfg = load_config()
    assert cfg['OUTLOOK_REFRESH_TOKEN'] == 'from-env'


def test_config_set_preserves_other_keys(tmp_config, clean_env):
    save_config({'OUTLOOK_REFRESH_TOKEN': 'rt', 'OUTLOOK_TENANT_ID': 'tid'})
    config_set('OUTLOOK_TENANT_ID', 'new-tid')
    cfg = load_config()
    assert cfg['OUTLOOK_REFRESH_TOKEN'] == 'rt'
    assert cfg['OUTLOOK_TENANT_ID'] == 'new-tid'


def test_config_set_rejects_unknown_key(tmp_config, clean_env):
    import pytest
    with pytest.raises(ValueError):
        config_set('EVIL_KEY', 'pwned')


def test_save_atomic_no_stray_tmpfile(tmp_config, clean_env):
    save_config({'OUTLOOK_REFRESH_TOKEN': 'x', 'OUTLOOK_TENANT_ID': 'y'})
    siblings = list(tmp_config.parent.iterdir())
    assert [p.name for p in siblings] == [tmp_config.name]
