"""Resource-group dispatcher + a representative handler from each verb
class. The full per-shortcut smoke matrix is intentionally not here -
each handler is 5-15 LOC and would test mostly the _argv parser. We
instead lock the contract: dispatcher peels the cross-cutting flags,
constructs RequestContext correctly, surfaces handler errors, and a
GET/POST/PATCH/DELETE shortcut each routes to the right Graph URL.
"""
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


def _capture_request(monkeypatch):
    """Replace api_request with a capture that records call kwargs and
    returns a generic empty-collection payload."""
    seen = {}

    def _fake(method, base, endpoint, token, **k):
        seen['method'] = method
        seen['endpoint'] = endpoint
        seen['body'] = k.get('body')
        seen['headers'] = k.get('extra_headers')
        return {'value': []}

    monkeypatch.setattr(cli.api_mod, 'api_request', _fake)
    return seen


# --- dispatcher behavior ---------------------------------------------------

def test_top_level_help_lists_groups(monkeypatch, capsys):
    assert _run(monkeypatch, 'help') == 0
    out = capsys.readouterr().out
    assert 'Resource groups' in out
    assert '\n  mail' in out
    assert '\n  me' in out


def test_group_help_lists_shortcuts(monkeypatch, capsys):
    assert _run(monkeypatch, 'mail') == 0
    out = capsys.readouterr().out
    assert 'owa-graph mail' in out
    assert '\n  list' in out
    assert '\n  send' in out
    # Common-flags reminder appears in group help, not top-level.
    assert '--pretty' in out
    assert '--ndjson' in out


def test_group_help_explicit(monkeypatch, capsys):
    assert _run(monkeypatch, 'me', 'help') == 0
    out = capsys.readouterr().out
    assert 'whoami' in out


def test_unknown_shortcut_errors(monkeypatch, capsys):
    rc = _run(monkeypatch, 'mail', 'frobnicate')
    err = capsys.readouterr().err
    assert rc == 1
    assert 'unknown mail shortcut' in err
    assert 'frobnicate' in err


def test_handler_value_error_surfaces_cleanly(monkeypatch, capsys):
    # mail.list does not accept --bogus; _argv.parse raises ValueError
    # which the dispatcher must catch and turn into rc=1 + stderr.
    _capture_request(monkeypatch)
    rc = _run(monkeypatch, 'mail', 'list', '--bogus', 'x')
    err = capsys.readouterr().err
    assert rc == 1
    assert 'unknown flag' in err


# --- representative handlers (one per verb class) --------------------------

def test_mail_list_default_inbox(monkeypatch):
    seen = _capture_request(monkeypatch)
    rc = _run(monkeypatch, 'mail', 'list')
    assert rc == 0
    assert seen['method'] == 'GET'
    assert '/me/mailFolders/Inbox/messages' in seen['endpoint']
    assert '$top=25' in seen['endpoint']


def test_mail_list_unread_filter_and_top(monkeypatch):
    seen = _capture_request(monkeypatch)
    rc = _run(monkeypatch, 'mail', 'list', '--unread', '--top', '5')
    assert rc == 0
    # build_url URL-quotes spaces as %20, not +.
    assert '$filter=isRead%20eq%20false' in seen['endpoint']
    assert '$top=5' in seen['endpoint']


def test_mail_send_post_body_shape(monkeypatch):
    seen = _capture_request(monkeypatch)
    rc = _run(
        monkeypatch, 'mail', 'send',
        '--to', 'a@x,b@x',
        '--subject', 'hi',
        '--body', 'hello',
    )
    assert rc == 0
    assert seen['method'] == 'POST'
    assert seen['endpoint'].endswith('/me/sendMail')
    body = seen['body']
    assert body['saveToSentItems'] is True
    assert body['message']['subject'] == 'hi'
    assert [r['emailAddress']['address'] for r in body['message']['toRecipients']] == ['a@x', 'b@x']
    assert body['message']['body']['content'] == 'hello'


def test_mail_send_missing_required_fails(monkeypatch, capsys):
    _capture_request(monkeypatch)
    rc = _run(monkeypatch, 'mail', 'send', '--to', 'a@x')
    captured = capsys.readouterr()
    assert rc == 2
    assert 'requires --subject and --to' in captured.err


def test_mail_flag_patches(monkeypatch):
    seen = _capture_request(monkeypatch)
    rc = _run(monkeypatch, 'mail', 'flag', '--id', 'abc')
    assert rc == 0
    assert seen['method'] == 'PATCH'
    assert seen['endpoint'].endswith('/me/messages/abc')
    assert seen['body'] == {'flag': {'flagStatus': 'flagged'}}


def test_mail_delete_sends_delete(monkeypatch):
    seen = _capture_request(monkeypatch)
    rc = _run(monkeypatch, 'mail', 'delete', '--id', 'abc')
    assert rc == 0
    assert seen['method'] == 'DELETE'
    assert seen['endpoint'].endswith('/me/messages/abc')


def test_me_whoami_pretty_indents_json(monkeypatch, capsys):
    """--pretty must be peeled off by the dispatcher before the handler
    sees argv (otherwise _argv.parse rejects it as unknown). For a single
    object format_pretty falls through to indented JSON."""
    def _fake(method, base, endpoint, token, **k):
        return {'displayName': 'Kim', 'mail': 'kim@example.com'}
    monkeypatch.setattr(cli.api_mod, 'api_request', _fake)
    rc = _run(monkeypatch, 'me', 'whoami', '--pretty')
    out = capsys.readouterr().out
    assert rc == 0
    # Indented form has newlines between fields; default JSON is one line.
    assert '\n  "displayName"' in out


def test_me_whoami_default_emits_json(monkeypatch, capsys):
    def _fake(method, base, endpoint, token, **k):
        return {'displayName': 'Kim'}
    monkeypatch.setattr(cli.api_mod, 'api_request', _fake)
    rc = _run(monkeypatch, 'me', 'whoami')
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out) == {'displayName': 'Kim'}


def test_ndjson_streams_collection_items(monkeypatch, capsys):
    def _fake(method, base, endpoint, token, **k):
        return {'value': [{'id': 'a'}, {'id': 'b'}]}
    monkeypatch.setattr(cli.api_mod, 'api_request', _fake)
    rc = _run(monkeypatch, 'mail', 'list', '--ndjson')
    out = capsys.readouterr().out
    assert rc == 0
    lines = [l for l in out.splitlines() if l.strip()]
    assert lines == ['{"id": "a"}', '{"id": "b"}']
