"""Shared fixtures for the owa-mail test suite.

No network. No real tokens. No writes outside tmp_path.
"""
import pytest


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect owa_mail.config.CONFIG_PATH to a path under tmp_path."""
    fake_path = tmp_path / 'owa-mail' / 'config'
    from owa_mail import config as config_mod
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', fake_path)
    return fake_path


@pytest.fixture
def clean_env(monkeypatch):
    """Strip OWA_* env vars so tests start from a known state."""
    for key in ('OWA_PROFILE', 'MAIL_DEBUG', 'XDG_CONFIG_HOME'):
        monkeypatch.delenv(key, raising=False)
