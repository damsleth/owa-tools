"""Shared fixtures for the owa-teams test suite.

No network. No real tokens. No writes outside tmp_path.
"""
import pytest


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect owa_teams.config.CONFIG_PATH under tmp_path so config I/O never
    touches the user's real file."""
    fake_path = tmp_path / 'owa-teams' / 'config'
    from owa_teams import config as config_mod
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', fake_path)
    return fake_path
