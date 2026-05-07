"""--count and --search shortcuts: query string + ConsistencyLevel
header semantics."""
import sys

import pytest

from owa_graph import cli


@pytest.fixture(autouse=True)
def _stub_auth_and_config(monkeypatch):
    monkeypatch.setattr(
        cli.auth_mod, 'setup_auth',
        lambda _c, audience='graph', beta=False, debug=False:
        ('tok', 'https://graph.microsoft.com/v1.0'),
    )
    monkeypatch.setattr(
        cli.config_mod, 'load_config',
        lambda: {'default_audience': 'graph'},
    )


def _run(monkeypatch, *args):
    monkeypatch.setattr(sys, 'argv', ['owa-graph', *args])
    return cli.main()


def test_count_adds_query_and_header(monkeypatch):
    seen = {}
    def _capture(method, base, endpoint, token, **k):
        seen['endpoint'] = endpoint
        seen['headers'] = k.get('extra_headers')
        return {'@odata.count': 42, 'value': []}
    monkeypatch.setattr(cli.api_mod, 'api_request', _capture)
    rc = _run(monkeypatch, 'GET', '/users', '--count')
    assert rc == 0
    assert '$count=true' in seen['endpoint']
    assert seen['headers'] == {'ConsistencyLevel': 'eventual'}


def test_search_wraps_in_double_quotes(monkeypatch):
    seen = {}
    def _capture(method, base, endpoint, token, **k):
        seen['endpoint'] = endpoint
        seen['headers'] = k.get('extra_headers')
        return {'value': []}
    monkeypatch.setattr(cli.api_mod, 'api_request', _capture)
    rc = _run(monkeypatch, 'GET', '/users', '--search', 'displayName:Bob')
    assert rc == 0
    # Quotes are URL-encoded: %22.
    assert '%22displayName%3ABob%22' in seen['endpoint']
    assert seen['headers']['ConsistencyLevel'] == 'eventual'


def test_search_renders_in_curl(monkeypatch, capsys):
    rc = _run(monkeypatch, 'GET', '/users', '--search', 'kim', '--curl')
    out = capsys.readouterr().out
    assert rc == 0
    assert '%22kim%22' in out
    # ConsistencyLevel reaches curl's -H list.
    assert 'ConsistencyLevel: eventual' in out


def test_count_does_not_overwrite_user_supplied_consistency_level(monkeypatch):
    seen = {}
    def _capture(method, base, endpoint, token, **k):
        seen['headers'] = k.get('extra_headers')
        return {'value': []}
    monkeypatch.setattr(cli.api_mod, 'api_request', _capture)
    rc = _run(
        monkeypatch, 'GET', '/users',
        '--header', 'ConsistencyLevel=session',
        '--count',
    )
    assert rc == 0
    # User's session value wins; --count's eventual is the fallback only.
    assert seen['headers']['ConsistencyLevel'] == 'session'


def test_count_and_search_combined(monkeypatch):
    seen = {}
    def _capture(method, base, endpoint, token, **k):
        seen['endpoint'] = endpoint
        return {'value': [], '@odata.count': 0}
    monkeypatch.setattr(cli.api_mod, 'api_request', _capture)
    _run(monkeypatch, 'GET', '/users', '--count', '--search', 'kim')
    assert '$count=true' in seen['endpoint']
    assert '%22kim%22' in seen['endpoint']
