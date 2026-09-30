"""Every tool's api_get passes `retry=` through to owa_core.http.request
(default 0: fail fast, as before)."""
import importlib
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('tool', ['mail', 'cal', 'people', 'planner', 'todo', 'drive'])
def test_api_get_forwards_retry(monkeypatch, tool):
    api = importlib.import_module(f'owa_{tool}.api')
    seen = []
    monkeypatch.setattr(
        api.http, 'request',
        lambda method, url, **kw: seen.append((method, kw['retry'])) or SimpleNamespace(json={}),
    )
    api.api_get('https://x.test', 'me', 'tok')
    api.api_get('https://x.test', 'me', 'tok', retry=2)
    assert seen == [('GET', 0), ('GET', 2)]
