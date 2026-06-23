"""owa_ado.api wrapper tests. owa_core.http.request is stubbed; no network."""
import pytest

from owa_ado import api
from owa_core.errors import AuthExpiredError, NotFoundError
from owa_core.http import Response


def test_build_url_appends_api_version_and_query():
    url = api.build_url('https://dev.azure.com/Org', '_apis/projects',
                        query={'$top': 5})
    assert url.startswith('https://dev.azure.com/Org/_apis/projects?')
    assert 'api-version=7.1' in url
    assert '%24top=5' in url


def test_build_url_drops_none_query_values():
    url = api.build_url('https://x', 'a', query={'keep': 1, 'drop': None})
    assert 'keep=1' in url and 'drop' not in url


def test_build_url_encodes_spaces_in_path_but_keeps_structure():
    url = api.build_url('https://x', 'ACME/ACME Team/_apis/work', api_version=None)
    assert 'ACME%20Team' in url
    assert '/_apis/work' in url  # slashes preserved


def test_build_url_keeps_dollar_in_path_for_create_route():
    url = api.build_url('https://x', 'P/_apis/wit/workitems/$Task', api_version=None)
    assert url.endswith('/_apis/wit/workitems/$Task')


def test_ado_request_passes_through_json(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen['method'] = method
        seen['url'] = url
        seen['headers'] = kwargs['headers']
        return Response(status=200, headers={}, json={'count': 1}, bytes=b'{}')

    monkeypatch.setattr(api.http, 'request', fake_request)
    out = api.ado_request('GET', 'https://x', '_apis/projects', 'tok',
                          extra_headers={'X': 'y'})
    assert out == {'count': 1}
    assert seen['method'] == 'GET'
    assert seen['headers'] == {'X': 'y'}


def test_ado_request_auth_error_reraises(monkeypatch):
    def fake_request(*a, **k):
        raise AuthExpiredError('nope')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(AuthExpiredError):
        api.ado_request('GET', 'https://x', 'a', 'tok')


def test_ado_request_notfound_raises(monkeypatch):
    def fake_request(*a, **k):
        raise NotFoundError('gone')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(NotFoundError):
        api.ado_request('GET', 'https://x', 'a', 'tok')


def test_ado_paginate_follows_continuation_header(monkeypatch):
    pages = [
        Response(status=200, headers={'x-ms-continuationtoken': 'C2'},
                 json={'value': [1, 2]}, bytes=b''),
        Response(status=200, headers={}, json={'value': [3]}, bytes=b''),
    ]
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(url)
        return pages[len(calls) - 1]

    monkeypatch.setattr(api.http, 'request', fake_request)
    out = api.ado_paginate('https://x', '_apis/git/repositories', 'tok')
    assert out == [1, 2, 3]
    assert len(calls) == 2
    assert 'continuationToken=C2' in calls[1]


def test_ado_paginate_respects_max_items(monkeypatch):
    def fake_request(method, url, **kwargs):
        return Response(status=200, headers={'x-ms-continuationtoken': 'more'},
                        json={'value': [1, 2, 3]}, bytes=b'')

    monkeypatch.setattr(api.http, 'request', fake_request)
    out = api.ado_paginate('https://x', 'a', 'tok', max_items=2)
    assert out == [1, 2]


def test_json_patch_sets_patch_media_type(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen['method'] = method
        seen['body'] = kwargs['body']
        seen['headers'] = kwargs['headers']
        return Response(status=200, headers={}, json={'id': 9}, bytes=b'{}')

    monkeypatch.setattr(api.http, 'request', fake_request)
    ops = [{'op': 'add', 'path': '/fields/System.Title', 'value': 'T'}]
    out = api.json_patch('POST', 'https://x', 'P/_apis/wit/workitems/$Task', 'tok',
                         operations=ops)
    assert out == {'id': 9}
    assert seen['method'] == 'POST'
    assert seen['body'] == ops
    assert seen['headers']['Content-Type'] == 'application/json-patch+json'
