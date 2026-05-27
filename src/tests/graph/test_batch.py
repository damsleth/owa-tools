"""batch subcommand: file/stdin sources, auto-wrap of flat arrays,
error paths."""
import io
import json
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


_BATCH_RESPONSE = {
    'responses': [
        {'id': '1', 'status': 200, 'body': {'displayName': 'kim'}},
        {'id': '2', 'status': 200, 'body': {'value': []}},
    ],
}


def test_batch_from_file_with_envelope(monkeypatch, tmp_path):
    body_file = tmp_path / 'batch.json'
    envelope = {'requests': [
        {'id': '1', 'method': 'GET', 'url': '/me'},
        {'id': '2', 'method': 'GET', 'url': '/me/messages'},
    ]}
    body_file.write_text(json.dumps(envelope))
    seen = {}
    def _capture(method, base, endpoint, token, body=None, **k):
        seen['method'] = method
        seen['endpoint'] = endpoint
        seen['body'] = body
        return _BATCH_RESPONSE
    monkeypatch.setattr(cli.api_mod, 'api_request', _capture)
    rc = _run(monkeypatch, 'batch', str(body_file))
    assert rc == 0
    assert seen['method'] == 'POST'
    assert seen['endpoint'] == '$batch'
    assert seen['body'] == envelope


def test_batch_flat_array_gets_auto_wrapped(monkeypatch, tmp_path):
    body_file = tmp_path / 'batch.json'
    body_file.write_text(json.dumps([
        {'id': '1', 'method': 'GET', 'url': '/me'},
    ]))
    seen = {}
    monkeypatch.setattr(
        cli.api_mod, 'api_request',
        lambda *a, **k: seen.update(body=k.get('body')) or _BATCH_RESPONSE,
    )
    rc = _run(monkeypatch, 'batch', str(body_file))
    assert rc == 0
    assert seen['body'] == {'requests': [{'id': '1', 'method': 'GET', 'url': '/me'}]}


def test_batch_at_prefix_path_supported(monkeypatch, tmp_path):
    body_file = tmp_path / 'batch.json'
    body_file.write_text('[]')
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: _BATCH_RESPONSE)
    rc = _run(monkeypatch, 'batch', f'@{body_file}')
    assert rc == 0


def test_batch_from_stdin(monkeypatch):
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps([
        {'id': '1', 'method': 'GET', 'url': '/me'},
    ])))
    seen = {}
    monkeypatch.setattr(
        cli.api_mod, 'api_request',
        lambda *a, **k: seen.update(body=k.get('body')) or _BATCH_RESPONSE,
    )
    rc = _run(monkeypatch, 'batch', '-')
    assert rc == 0
    assert seen['body'] == {'requests': [{'id': '1', 'method': 'GET', 'url': '/me'}]}


def test_batch_pretty_renders(monkeypatch, tmp_path, capsys):
    body_file = tmp_path / 'batch.json'
    body_file.write_text('[]')
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: _BATCH_RESPONSE)
    rc = _run(monkeypatch, 'batch', str(body_file), '--pretty')
    out = capsys.readouterr().out
    assert rc == 0
    # Pretty path renders indented JSON for unknown shape.
    assert '\n  ' in out


def test_batch_default_emits_compact_json(monkeypatch, tmp_path, capsys):
    body_file = tmp_path / 'batch.json'
    body_file.write_text('[]')
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: _BATCH_RESPONSE)
    rc = _run(monkeypatch, 'batch', str(body_file))
    out = capsys.readouterr().out
    assert rc == 0
    # Compact form, no leading whitespace per nested key.
    assert '\n' not in out.strip()
    assert json.loads(out) == _BATCH_RESPONSE


def test_batch_ndjson_streams_one_response_per_line(monkeypatch, tmp_path, capsys):
    body_file = tmp_path / 'batch.json'
    body_file.write_text('[]')
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: _BATCH_RESPONSE)
    rc = _run(monkeypatch, 'batch', str(body_file), '--ndjson')
    out = capsys.readouterr().out
    assert rc == 0
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 2
    assert [json.loads(ln) for ln in lines] == _BATCH_RESPONSE['responses']


def test_batch_ndjson_non_envelope_emits_single_line(monkeypatch, tmp_path, capsys):
    body_file = tmp_path / 'batch.json'
    body_file.write_text('[]')
    # An error-shaped response without a `responses` list still yields
    # valid NDJSON: one line for the whole document.
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: {'error': 'nope'})
    rc = _run(monkeypatch, 'batch', str(body_file), '--ndjson')
    out = capsys.readouterr().out
    assert rc == 0
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0]) == {'error': 'nope'}


def test_batch_ndjson_and_pretty_incompatible(monkeypatch, tmp_path, capsys):
    body_file = tmp_path / 'batch.json'
    body_file.write_text('[]')
    rc = _run(monkeypatch, 'batch', str(body_file), '--ndjson', '--pretty')
    assert rc != 0
    assert 'incompatible' in capsys.readouterr().err


def test_batch_no_source_errors(monkeypatch, capsys):
    rc = _run(monkeypatch, 'batch')
    err = capsys.readouterr().err
    assert rc == 1
    assert 'requires a file path or - for stdin' in err


def test_batch_unknown_flag(monkeypatch, capsys):
    rc = _run(monkeypatch, 'batch', '--bogus')
    err = capsys.readouterr().err
    assert rc == 1
    assert 'Unknown flag' in err


def test_batch_extra_positional(monkeypatch, tmp_path, capsys):
    f = tmp_path / 'b.json'
    f.write_text('[]')
    rc = _run(monkeypatch, 'batch', str(f), 'extra-arg')
    assert rc == 1
    assert 'Unexpected argument' in capsys.readouterr().err


def test_batch_missing_file(monkeypatch, tmp_path, capsys):
    rc = _run(monkeypatch, 'batch', str(tmp_path / 'nonexistent.json'))
    assert rc == 1
    assert 'cannot read' in capsys.readouterr().err


def test_batch_invalid_json(monkeypatch, tmp_path, capsys):
    f = tmp_path / 'bad.json'
    f.write_text('this is not json')
    rc = _run(monkeypatch, 'batch', str(f))
    assert rc == 1
    assert 'not valid JSON' in capsys.readouterr().err


def test_batch_object_without_requests_key(monkeypatch, tmp_path, capsys):
    f = tmp_path / 'b.json'
    f.write_text(json.dumps({'unrelated': []}))
    rc = _run(monkeypatch, 'batch', str(f))
    assert rc == 1
    err = capsys.readouterr().err
    assert "must be a list of requests" in err


def test_batch_scalar_body_rejected(monkeypatch, tmp_path, capsys):
    f = tmp_path / 'b.json'
    f.write_text('"just a string"')
    rc = _run(monkeypatch, 'batch', str(f))
    assert rc == 1


def test_batch_api_failure_returns_1(monkeypatch, tmp_path):
    f = tmp_path / 'b.json'
    f.write_text('[]')
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: None)
    rc = _run(monkeypatch, 'batch', str(f))
    assert rc == 1


def test_batch_retry_flag_forwarded(monkeypatch, tmp_path):
    f = tmp_path / 'b.json'
    f.write_text('[]')
    seen = {}
    def _capture(method, base, endpoint, token, **k):
        seen['retry'] = k.get('retry')
        return _BATCH_RESPONSE
    monkeypatch.setattr(cli.api_mod, 'api_request', _capture)
    _run(monkeypatch, 'batch', str(f), '--retry')
    assert seen['retry'] is True
