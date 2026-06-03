import pytest


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Point owa_vids.config at a throwaway path so tests never touch
    the real ~/.config/owa-vids/config."""
    from owa_vids import config as config_mod
    fake = tmp_path / 'owa-vids' / 'config'
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', fake)
    return fake


@pytest.fixture
def clean_env(monkeypatch):
    for key in ('OWA_PROFILE', 'OWA_AGENT', 'OWA_ERR_JSON', 'VIDS_DEBUG',
                'XDG_CONFIG_HOME'):
        monkeypatch.delenv(key, raising=False)
