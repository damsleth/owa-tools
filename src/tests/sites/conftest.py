"""Shared fixtures for the owa-sites test suite.

No network. No real tokens. No writes outside tmp_path.
"""
import pytest


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect owa_sites.config.CONFIG_PATH under tmp_path so config I/O never
    touches the user's real file."""
    fake_path = tmp_path / 'owa-sites' / 'config'
    from owa_sites import config as config_mod
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', fake_path)
    return fake_path
