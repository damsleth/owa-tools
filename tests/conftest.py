"""Shared fixtures for the cal-cli test suite.

No network. No real tokens. No writes outside tmp_path.
"""
import pytest


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect cal_cli.config.CONFIG_PATH to a path under tmp_path."""
    fake_path = tmp_path / 'cal-cli' / 'config'
    from cal_cli import config as config_mod
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', fake_path)
    return fake_path


@pytest.fixture
def clean_env(monkeypatch):
    """Strip OUTLOOK_* env vars so tests start from a known state."""
    for key in (
        'OUTLOOK_REFRESH_TOKEN', 'OUTLOOK_TENANT_ID', 'OUTLOOK_APP_CLIENT_ID',
        'OWA_PROFILE', 'CAL_DEBUG', 'XDG_CONFIG_HOME',
    ):
        monkeypatch.delenv(key, raising=False)
