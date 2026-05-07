"""Config file IO. Covers parse, write-allowlist, atomic-rename,
and env-var override precedence."""
import pytest

from owa_graph import config as config_mod


@pytest.fixture
def tmp_config(monkeypatch, tmp_path):
    """Redirect CONFIG_PATH to a temp dir for the duration of one test."""
    target = tmp_path / 'owa-graph' / 'config'
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', target)
    monkeypatch.delenv('GRAPH_APP_CLIENT_ID', raising=False)
    return target


def test_parse_lines_handles_quoted_and_bare(tmp_config):
    text = '''
GRAPH_TENANT_ID="abc-def"
owa_piggy_profile=work
# comment
default_audience='graph'
malformed line
'''
    out = config_mod._parse_lines(text)
    assert out == {
        'GRAPH_TENANT_ID': 'abc-def',
        'owa_piggy_profile': 'work',
        'default_audience': 'graph',
    }


def test_parse_kv_stream_drops_unknown_keys(tmp_config):
    text = 'GRAPH_TENANT_ID="x"\nUNKNOWN_KEY="y"\n'
    assert config_mod.parse_kv_stream(text) == {'GRAPH_TENANT_ID': 'x'}


def test_load_config_default_audience_when_no_file(tmp_config):
    cfg = config_mod.load_config()
    assert cfg['default_audience'] == 'graph'


def test_load_config_reads_file(tmp_config):
    tmp_config.parent.mkdir(parents=True, exist_ok=True)
    tmp_config.write_text('owa_piggy_profile="work"\nGRAPH_TENANT_ID="t1"\n')
    cfg = config_mod.load_config()
    assert cfg['owa_piggy_profile'] == 'work'
    assert cfg['GRAPH_TENANT_ID'] == 't1'
    assert cfg['default_audience'] == 'graph'


def test_load_config_env_overrides_file(tmp_config, monkeypatch):
    tmp_config.parent.mkdir(parents=True, exist_ok=True)
    tmp_config.write_text('GRAPH_APP_CLIENT_ID="from-file"\n')
    monkeypatch.setenv('GRAPH_APP_CLIENT_ID', 'from-env')
    cfg = config_mod.load_config()
    assert cfg['GRAPH_APP_CLIENT_ID'] == 'from-env'


def test_save_config_writes_atomically_with_0600(tmp_config):
    config_mod.save_config({'owa_piggy_profile': 'work'})
    assert tmp_config.exists()
    content = tmp_config.read_text()
    assert 'owa_piggy_profile="work"' in content
    mode = tmp_config.stat().st_mode & 0o777
    assert mode == 0o600


def test_save_config_preserves_existing_lines(tmp_config):
    tmp_config.parent.mkdir(parents=True, exist_ok=True)
    tmp_config.write_text(
        '# pinned comment\n'
        'GRAPH_TENANT_ID="t1"\n'
        'unknown_key="kept"\n'
    )
    config_mod.save_config({'owa_piggy_profile': 'new'})
    content = tmp_config.read_text()
    assert '# pinned comment' in content
    assert 'unknown_key="kept"' in content
    assert 'owa_piggy_profile="new"' in content


def test_save_config_overwrites_existing_key_in_place(tmp_config):
    tmp_config.parent.mkdir(parents=True, exist_ok=True)
    tmp_config.write_text('GRAPH_TENANT_ID="old"\n')
    config_mod.save_config({'GRAPH_TENANT_ID': 'new'})
    assert 'GRAPH_TENANT_ID="new"' in tmp_config.read_text()
    assert 'old' not in tmp_config.read_text()


def test_config_set_rejects_unknown_key(tmp_config):
    with pytest.raises(ValueError, match='unknown config key'):
        config_mod.config_set('SOMETHING_RANDOM', 'value')


def test_config_set_persists_value(tmp_config):
    config_mod.config_set('owa_piggy_profile', 'work')
    config_mod.config_set('GRAPH_APP_CLIENT_ID', 'abc')
    cfg = config_mod.load_config()
    assert cfg['owa_piggy_profile'] == 'work'
    assert cfg['GRAPH_APP_CLIENT_ID'] == 'abc'


def test_save_config_creates_parent_dir(tmp_config):
    assert not tmp_config.parent.exists()
    config_mod.save_config({'owa_piggy_profile': 'x'})
    assert tmp_config.parent.exists()
