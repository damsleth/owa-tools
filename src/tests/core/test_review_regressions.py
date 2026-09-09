"""Regression cases for the September source review; all transport is synthetic."""
import io
import json
from contextlib import redirect_stderr
from http.client import IncompleteRead

import pytest

from owa_core import http, modes
from owa_core.errors import NetworkError
from owa_core.secrets import safe_url
from owa_core.timezones import resolve_timezone


@pytest.mark.parametrize('helper', [http.request, http.request_unauthenticated])
@pytest.mark.parametrize('failure', [TimeoutError(), ConnectionResetError(), IncompleteRead(b'partial')])
@pytest.mark.parametrize('during_read', [False, True])
def test_transport_failures_map_to_network(helper, failure, during_read):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            raise failure

    def transport(*args, **kwargs):
        if during_read:
            return Response()
        raise failure

    kwargs = {'token': 'fake'} if helper is http.request else {}
    with pytest.raises(NetworkError) as err:
        helper('GET', 'https://example.invalid/', urlopen=transport, **kwargs)
    assert err.value.exit_code == 10
    assert err.value.cause is failure


@pytest.mark.parametrize('helper', [http.request, http.request_unauthenticated])
def test_debug_url_omits_capabilities(helper):
    url = 'https://user:opaque-password@example.invalid/upload?sig=opaque-signature#private'
    kwargs = {'token': 'fake'} if helper is http.request else {}
    with redirect_stderr(io.StringIO()) as out, pytest.raises(NetworkError):
        helper('PUT', url, debug=True, urlopen=lambda *a, **k: (_ for _ in ()).throw(TimeoutError()), **kwargs)
    assert 'https://example.invalid/upload' in out.getvalue()
    assert all(secret not in out.getvalue() for secret in ['opaque-password', 'opaque-signature', 'private'])
    assert safe_url('https://[invalid') == '[redacted-url]'


@pytest.mark.parametrize('mode', [[], ['--pretty'], ['--ndjson']])
def test_fanout_errors_are_redacted(mode, capsys):
    token = '.'.join(['A' * 12, 'B' * 12, 'C' * 12])

    def dispatch(argv):
        raise NetworkError(token + ' ' + json.dumps({'content': 'private "body remainder"'}))

    assert modes.run_with_output_modes('fake', ['read', '--profile', 'a', '--profile', 'b', *mode], dispatch) == 1
    out = capsys.readouterr().out
    assert token not in out and 'body remainder' not in out
    assert '[redacted-secret]' in out


@pytest.mark.parametrize('mixed,expected', [(False, 1), (True, 2)])
def test_fanout_invalid_json_agrees_with_exit(mixed, expected, capsys):
    def dispatch(argv):
        print('{}' if mixed and argv[-1] == 'a' else 'not json')
        return 0

    assert modes.run_with_output_modes('fake', ['read', '--profile', 'a', '--profile', 'b'], dispatch) == expected
    records = json.loads(capsys.readouterr().out)['results']
    assert records[-1]['ok'] is False and records[-1]['exit_code'] == 2


def test_leading_global_values_are_not_commands():
    assert modes.command_name(['--profile', 'work', '--audience', 'graph', 'get']) == 'get'
    assert modes.command_name(['--profile=work', 'get']) == 'get'
    assert modes.command_name(['--profile', 'work']) == ''


def test_pagination_only_signals_real_truncation():
    def run(next_link):
        class Response(io.BytesIO):
            status = 200
            headers = {}
        calls = []
        items = list(http.paginate(
            'https://example.invalid/', token='fake', max_pages=1,
            on_truncate=lambda *args: calls.append(args),
            urlopen=lambda *a, **k: Response(json.dumps({'value': [1], '@odata.nextLink': next_link}).encode()),
        ))
        assert items == [1]
        return calls
    assert run(None) == []
    assert run('https://example.invalid/next') == [(1, 'https://example.invalid/next')]


def test_typed_timeout_through_agent_dispatch(capsys):
    def dispatch(argv):
        return http.request('GET', 'https://example.invalid', token='fake',
                            urlopen=lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    assert modes.run_with_output_modes('fake', ['read', '--agent', '--err-json'], dispatch) == 10
    captured = capsys.readouterr()
    assert captured.out == ''
    assert json.loads(captured.err)['error']['exit_code'] == 10


def test_timezone_resolution_is_strict():
    from owa_core.errors import UsageError
    assert resolve_timezone('Pacific Standard Time').key == 'America/Los_Angeles'
    assert resolve_timezone('Europe/Oslo').key == 'Europe/Oslo'
    with pytest.raises(UsageError):
        resolve_timezone('Unknown Standard Time')
