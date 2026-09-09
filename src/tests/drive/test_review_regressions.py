import json

import pytest

from owa import cli as umbrella
from owa_core.errors import AuthExpiredError, ConflictError, NetworkError, NotFoundError
from owa_core.http import Response
from owa_drive import api, cli


@pytest.mark.parametrize('error', [NetworkError, AuthExpiredError])
def test_preflight_failure_never_uploads(monkeypatch, error):
    monkeypatch.setattr(cli.http_mod, 'request', lambda *a, **k: (_ for _ in ()).throw(error('fake')))
    monkeypatch.setattr(cli, '_upload_one', lambda *a, **k: pytest.fail('must not upload'))
    with pytest.raises(error):
        cli.cmd_put(['fake', '/existing.txt'], {}, 'fake', 'https://example.invalid')


@pytest.mark.parametrize('large', [False, True])
@pytest.mark.parametrize('force', [False, True])
def test_conflict_policy_reaches_server(monkeypatch, tmp_path, large, force):
    source = tmp_path / 'file'
    source.write_bytes(b'12345')
    monkeypatch.setattr(api, 'UPLOAD_LIMIT_BYTES', 4 if large else 10)
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == 'GET':
            raise NotFoundError('missing')
        policy = kwargs['body']['item']['@microsoft.graph.conflictBehavior'] if large else url.split('conflictBehavior=')[1]
        assert policy == ('replace' if force else 'fail')
        # Simulate a competing create after the preflight, rejected by the server.
        if not force:
            raise ConflictError('concurrent create')
        return Response(200, {}, {'uploadUrl':'https://example.invalid/upload'} if large else {'id':'fake'}, b'')

    monkeypatch.setattr(api.http, 'request', request)
    monkeypatch.setattr(api.upload_mod, 'upload_session', lambda *a, **k: {'id':'fake'})
    args = [str(source), '/file'] + (['--force'] if force else [])
    if force:
        assert cli.cmd_put(args, {}, 'fake', 'https://example.invalid') == 0
    else:
        with pytest.raises(ConflictError):
            cli.cmd_put(args, {}, 'fake', 'https://example.invalid')
    assert any(method == ('POST' if large else 'PUT') for method, _, _ in calls)


@pytest.mark.parametrize('command', ['get', 'download'])
@pytest.mark.parametrize('before', [True, False])
@pytest.mark.parametrize('via_umbrella', [True, False])
def test_binary_agent_guard_precedes_auth(monkeypatch, command, before, via_umbrella, capsys):
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', lambda *a, **k: pytest.fail('guard must precede auth'))
    profile = ['--profile', 'work']
    args = (profile if before else []) + [command, '/file'] + ([] if before else profile) + ['--agent']
    rc = umbrella.main(['drive', *args]) if via_umbrella else cli.main(args)
    assert rc == 2
    output = capsys.readouterr()
    assert output.out == '' and 'binary output' in output.err


@pytest.mark.parametrize('command', ['get', 'download'])
def test_binary_fanout_guard(monkeypatch, command):
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', lambda *a, **k: pytest.fail('guard must precede auth'))
    assert cli.main([command, '/file', '--profile', 'a', '--profile', 'b']) == 2


def test_umbrella_agent_download_to_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', lambda *a, **k: ('fake','https://example.invalid'))
    monkeypatch.setattr(cli.api_mod, 'api_get_binary', lambda *a, **k: b'bytes')
    out = tmp_path / 'download'
    assert umbrella.main(['--agent', 'drive', '--profile', 'work', 'download', '/file', '--out', str(out)]) == 0
    assert out.read_bytes() == b'bytes'
    payload = json.loads(capsys.readouterr().out)
    assert payload['_owa']['tool'] == 'owa-drive'
    assert payload['_owa']['command'] == 'get'
