"""Shared fixtures for the owa-sched test suite. No network."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    fake_path = tmp_path / 'owa-sched' / 'config'
    from owa_sched import config as config_mod
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', fake_path)
    return fake_path


@pytest.fixture
def clean_env(monkeypatch):
    for key in ('OWA_PROFILE', 'SCHED_DEBUG', 'XDG_CONFIG_HOME'):
        monkeypatch.delenv(key, raising=False)
