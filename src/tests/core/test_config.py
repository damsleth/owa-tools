from owa_core import config


def test_load_config_file_ignores_stale_profile_pin(tmp_path):
    path = tmp_path / 'config'
    path.write_text('owa_piggy_profile="nc"\ndefault_audience="graph"\n')
    assert config.load_config_file(path) == {'default_audience': 'graph'}


def test_ado_keeps_its_profile_pin(tmp_path, monkeypatch):
    from owa_ado import config as ado_config
    path = tmp_path / 'config'
    path.write_text('owa_piggy_profile="nc"\nado_org="org"\n')
    monkeypatch.setattr(ado_config, 'CONFIG_PATH', path)
    assert ado_config.load_config() == {'owa_piggy_profile': 'nc', 'ado_org': 'org'}
    monkeypatch.setattr(ado_config, 'CONFIG_PATH', tmp_path / 'missing')
    assert ado_config.load_config() == {}
