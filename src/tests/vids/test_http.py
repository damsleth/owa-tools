"""Keep-alive Http client tests - http.client boundary mocked."""
import http.client

import pytest

from owa_core.errors import AuthExpiredError, NetworkError
from owa_vids import http as http_mod


class FakeResponse:
    def __init__(self, status, body, headers=None):
        self.status = status
        self._body = body
        self._headers = headers or {}

    def read(self):
        return self._body

    def getheader(self, name):
        return self._headers.get(name)


class FakeConnection:
    """Scripted responses/exceptions shared across instances via the harness."""

    def __init__(self, harness, host, timeout=None):
        self.harness = harness
        self.host = host
        self.timeout = timeout
        self.closed = False
        harness.instances.append(self)

    def request(self, method, path, headers=None):
        self.harness.requests.append((method, path, dict(headers or {})))
        nxt = self.harness.script[0]
        if isinstance(nxt, Exception):
            self.harness.script.pop(0)
            raise nxt

    def getresponse(self):
        nxt = self.harness.script.pop(0)
        return FakeResponse(*nxt)

    def close(self):
        self.closed = True


class Harness:
    def __init__(self, script):
        self.script = list(script)
        self.instances = []
        self.requests = []
        self.sleeps = []


@pytest.fixture
def make_http(monkeypatch):
    """Return (Http, harness) with HTTPSConnection and time.sleep stubbed."""

    def factory(script, debug=False):
        harness = Harness(script)
        monkeypatch.setattr(
            http_mod.http.client, 'HTTPSConnection',
            lambda host, timeout=None: FakeConnection(harness, host, timeout),
        )
        monkeypatch.setattr(http_mod.time, 'sleep', harness.sleeps.append)
        return http_mod.Http(debug=debug), harness

    return factory


def test_get_success_sets_user_agent(make_http):
    client, harness = make_http([(200, b'data', {})])
    status, data = client.get('https://h.svc.ms/seg?x=1')
    assert (status, data) == (200, b'data')
    method, path, headers = harness.requests[0]
    assert method == 'GET'
    assert path == '/seg?x=1'
    assert headers['User-Agent'] == http_mod.UA
    assert harness.sleeps == []


def test_get_reuses_connection_per_host(make_http):
    client, harness = make_http([(200, b'a', {}), (200, b'b', {})])
    client.get('https://h.svc.ms/one')
    client.get('https://h.svc.ms/two')
    assert len(harness.instances) == 1


def test_get_retries_transient_honoring_retry_after(make_http):
    client, harness = make_http([(429, b'', {'Retry-After': '7'}), (200, b'ok', {})])
    status, data = client.get('https://h.svc.ms/seg')
    assert (status, data) == (200, b'ok')
    assert harness.sleeps == [7]
    # The throttled connection is recycled before the retry.
    assert len(harness.instances) == 2
    assert harness.instances[0].closed


def test_get_treats_empty_200_as_transient(make_http):
    client, harness = make_http([(200, b'', {}), (200, b'ok', {})])
    status, data = client.get('https://h.svc.ms/seg')
    assert (status, data) == (200, b'ok')
    assert len(harness.sleeps) == 1


def test_get_passes_auth_statuses_straight_back(make_http):
    client, harness = make_http([(401, b'denied', {})])
    status, data = client.get('https://h.svc.ms/seg')
    assert (status, data) == (401, b'denied')
    assert harness.sleeps == []
    assert len(harness.requests) == 1


def test_get_retries_connection_errors_on_fresh_connection(make_http):
    client, harness = make_http([OSError('reset'), (200, b'ok', {})])
    status, data = client.get('https://h.svc.ms/seg')
    assert (status, data) == (200, b'ok')
    assert len(harness.sleeps) == 1
    assert len(harness.instances) == 2


def test_get_exhausted_transient_returns_last_status(make_http):
    client, harness = make_http([(503, b'busy', {})] * 3)
    status, data = client.get('https://h.svc.ms/seg', tries=3)
    assert (status, data) == (503, b'busy')
    assert len(harness.sleeps) == 3


def test_get_all_connection_errors_raises_without_query(make_http):
    client, harness = make_http([http.client.HTTPException('boom')] * 2)
    with pytest.raises(NetworkError) as exc:
        client.get('https://h.svc.ms/seg?access_token=SECRET', tries=2)
    assert 'SECRET' not in str(exc.value)
    assert '/seg' in str(exc.value)


def test_get_debug_logs_backoff(make_http, capsys):
    client, harness = make_http([(429, b'', {}), (200, b'ok', {})], debug=True)
    client.get('https://h.svc.ms/seg')
    assert 'backoff' in capsys.readouterr().err


class StubClient:
    def __init__(self, status, body):
        self.status, self.body = status, body
        self.calls = []

    def get(self, url, headers=None, *, tries=8):
        self.calls.append((url, dict(headers or {})))
        return self.status, self.body


def test_graph_get_parses_json_and_sends_bearer():
    stub = StubClient(200, b'{"a": 1}')
    out = http_mod.graph_get(stub, 'tok', 'https://graph/x')
    assert out == {'a': 1}
    assert stub.calls[0][1]['Authorization'] == 'Bearer tok'


def test_graph_get_401_raises_auth_expired():
    with pytest.raises(AuthExpiredError):
        http_mod.graph_get(StubClient(401, b'denied'), 'tok', 'https://graph/x')


def test_graph_get_500_raises_network_error():
    with pytest.raises(NetworkError):
        http_mod.graph_get(StubClient(500, b'oops'), 'tok', 'https://graph/x')
