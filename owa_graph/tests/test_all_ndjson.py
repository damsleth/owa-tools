"""--all and --ndjson coverage at the CLI level."""
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


def test_all_collects_into_value_wrapper(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'paginate',
        lambda *a, **k: iter([{'id': 1}, {'id': 2}, {'id': 3}]),
    )
    rc = _run(monkeypatch, 'GET', '/users', '--all')
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert parsed == {'value': [{'id': 1}, {'id': 2}, {'id': 3}]}


def test_all_with_ndjson_streams_one_per_line(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'paginate',
        lambda *a, **k: iter([{'id': 1}, {'id': 2}]),
    )
    rc = _run(monkeypatch, 'GET', '/users', '--all', '--ndjson')
    out = capsys.readouterr().out
    assert rc == 0
    lines = out.strip().split('\n')
    assert [json.loads(l) for l in lines] == [{'id': 1}, {'id': 2}]


def test_all_with_pretty_renders_table(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'paginate',
        lambda *a, **k: iter([
            {'displayName': 'A', 'userPrincipalName': 'a@x.com', 'id': 'x'},
        ]),
    )
    rc = _run(monkeypatch, 'GET', '/users', '--all', '--pretty')
    out = capsys.readouterr().out
    assert rc == 0
    assert 'a@x.com' in out
    assert '"value"' not in out  # not raw JSON


def test_ndjson_single_response_with_value_list(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'api_request',
        lambda *a, **k: {'value': [{'id': 1}, {'id': 2}], '@odata.context': 'x'},
    )
    rc = _run(monkeypatch, 'GET', '/users', '--ndjson')
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip().split('\n') == ['{"id": 1}', '{"id": 2}']


def test_ndjson_single_entity_one_line(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'api_request',
        lambda *a, **k: {'displayName': 'kim', 'id': 'x'},
    )
    rc = _run(monkeypatch, 'GET', '/me', '--ndjson')
    out = capsys.readouterr().out
    assert rc == 0
    assert out.count('\n') == 1
    assert json.loads(out.strip()) == {'displayName': 'kim', 'id': 'x'}


def test_all_empty_collection_returns_zero(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'paginate', lambda *a, **k: iter([]))
    rc = _run(monkeypatch, 'GET', '/users', '--all', '--ndjson')
    out = capsys.readouterr().out
    assert rc == 0
    assert out == ''


def test_all_empty_default_emits_value_empty(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'paginate', lambda *a, **k: iter([]))
    rc = _run(monkeypatch, 'GET', '/users', '--all')
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out) == {'value': []}


def test_all_plus_raw_is_rejected(monkeypatch, capsys):
    rc = _run(monkeypatch, 'GET', '/users', '--all', '--raw')
    err = capsys.readouterr().err
    assert rc == 1
    assert '--all and --raw are incompatible' in err


def test_ndjson_plus_raw_is_rejected(monkeypatch, capsys):
    rc = _run(monkeypatch, 'GET', '/me/photo/$value', '--ndjson', '--raw')
    err = capsys.readouterr().err
    assert rc == 1
    assert '--ndjson and --raw are incompatible' in err


def test_retry_flag_forwarded_to_api_request(monkeypatch):
    seen = {}
    def _capture(method, base, endpoint, token, **k):
        seen['retry'] = k.get('retry')
        return {'ok': True}
    monkeypatch.setattr(cli.api_mod, 'api_request', _capture)
    _run(monkeypatch, 'GET', '/me', '--retry')
    assert seen['retry'] is True


def test_retry_flag_forwarded_to_paginate(monkeypatch):
    seen = {}
    def _capture(method, url, token, **k):
        seen['retry'] = k.get('retry')
        return iter([{'id': 1}])
    monkeypatch.setattr(cli.api_mod, 'paginate', _capture)
    _run(monkeypatch, 'GET', '/users', '--all', '--retry')
    assert seen['retry'] is True
