"""Config file I/O tests."""


def test_config_set_creates_file(tmp_config, clean_env):
    from owa_people import config as config_mod
    config_mod.config_set('owa_piggy_profile', 'work')
    assert tmp_config.exists()
    content = tmp_config.read_text()
    assert 'owa_piggy_profile="work"' in content


def test_config_set_chmods_0600(tmp_config, clean_env):
    from owa_people import config as config_mod
    config_mod.config_set('owa_piggy_profile', 'work')
    mode = tmp_config.stat().st_mode & 0o777
    assert mode == 0o600


def test_config_set_rejects_unknown_key(tmp_config, clean_env):
    from owa_people import config as config_mod
    import pytest
    with pytest.raises(ValueError):
        config_mod.config_set('access_token', 'oops')


def test_load_config_round_trip(tmp_config, clean_env):
    from owa_people import config as config_mod
    config_mod.config_set('owa_piggy_profile', 'crayon')
    cfg = config_mod.load_config()
    assert cfg.get('owa_piggy_profile') == 'crayon'


def test_parse_kv_filters_unknown_keys():
    from owa_people import config as config_mod
    raw = (
        'owa_piggy_profile="x"\n'
        'access_token="should-be-dropped"\n'
        'debug="1"\n'
    )
    parsed = config_mod.parse_kv_stream(raw)
    assert parsed == {'owa_piggy_profile': 'x', 'debug': '1'}
