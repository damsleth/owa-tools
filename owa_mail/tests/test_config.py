"""Tests for config file I/O."""
import stat

import pytest

from owa_mail.config import (
    config_set,
    load_config,
    parse_kv_stream,
    save_config,
)


def test_parse_kv_stream_basic():
    out = parse_kv_stream('owa_piggy_profile=work\ndebug=1\n')
    assert out == {'owa_piggy_profile': 'work', 'debug': '1'}


def test_parse_kv_stream_strips_quotes():
    out = parse_kv_stream('owa_piggy_profile="work"\ndebug=\'1\'\n')
    assert out == {'owa_piggy_profile': 'work', 'debug': '1'}


def test_parse_kv_stream_rejects_unknown_keys():
    out = parse_kv_stream('EVIL=1\nowa_piggy_profile=ok\n')
    assert out == {'owa_piggy_profile': 'ok'}


def test_parse_kv_stream_ignores_comments_and_blanks():
    out = parse_kv_stream('\n# comment\nowa_piggy_profile=work\n\n')
    assert out == {'owa_piggy_profile': 'work'}


def test_load_config_missing_file(tmp_config, clean_env):
    assert not tmp_config.exists()
    cfg = load_config()
    assert cfg == {}


def test_save_and_load_roundtrip(tmp_config, clean_env):
    save_config({'owa_piggy_profile': 'work'})
    cfg = load_config()
    assert cfg['owa_piggy_profile'] == 'work'


def test_save_sets_0600(tmp_config, clean_env):
    save_config({'owa_piggy_profile': 'work'})
    mode = stat.S_IMODE(tmp_config.stat().st_mode)
    assert mode == 0o600


def test_owa_piggy_profile_roundtrip(tmp_config, clean_env):
    save_config({'owa_piggy_profile': 'work'})
    cfg = load_config()
    assert cfg['owa_piggy_profile'] == 'work'


def test_parse_kv_stream_preserves_profile_key():
    out = parse_kv_stream('owa_piggy_profile="work"\n')
    assert out == {'owa_piggy_profile': 'work'}


def test_config_set_preserves_unknown_lines(tmp_config, clean_env):
    """save_config preserves unknown keys/lines from the existing file
    on its read-and-rewrite path. Verifies hand-edits survive."""
    tmp_config.parent.mkdir(parents=True, exist_ok=True)
    tmp_config.write_text(
        '# user comment\n'
        'owa_piggy_profile="work"\n'
        'CUSTOM_THING="kept"\n'
    )
    config_set('owa_piggy_profile', 'home')
    text = tmp_config.read_text()
    assert 'owa_piggy_profile="home"' in text
    assert 'CUSTOM_THING="kept"' in text
    assert '# user comment' in text


def test_config_set_rejects_unknown_key(tmp_config, clean_env):
    with pytest.raises(ValueError):
        config_set('EVIL_KEY', 'pwned')


def test_save_no_stray_files(tmp_config, clean_env):
    save_config({'owa_piggy_profile': 'work'})
    siblings = list(tmp_config.parent.iterdir())
    assert [p.name for p in siblings] == [tmp_config.name]
