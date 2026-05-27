"""Shared fixtures for the owa-todo test suite.

No network. No real tokens. No writes outside tmp_path.
"""
import os
import time

import pytest


@pytest.fixture(autouse=True)
def _force_utc():
    """Pin the process timezone to UTC so task-date normalization is
    deterministic regardless of where the suite runs (To Do stores date
    fields in UTC; owa_todo.tasks.to_local converts to the host zone)."""
    original = os.environ.get('TZ')
    os.environ['TZ'] = 'UTC'
    if hasattr(time, 'tzset'):
        time.tzset()
    try:
        yield
    finally:
        if original is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = original
        if hasattr(time, 'tzset'):
            time.tzset()


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect owa_todo.config.CONFIG_PATH under tmp_path so config I/O
    never touches the user's real file."""
    fake_path = tmp_path / 'owa-todo' / 'config'
    from owa_todo import config as config_mod
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', fake_path)
    return fake_path
