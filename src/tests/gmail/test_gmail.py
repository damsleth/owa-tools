"""owa-gmail: normalizers, query builder, pagination, CLI and auth. No network."""
import base64
import json

import pytest

from owa_core.auth import BrokerProfile, BrokerToken
from owa_core.errors import AuthExpiredError, ConflictError, UsageError
from owa_gmail import api, auth, cli, format, messages

BASE = 'https://gmail.test/users/me'


def _b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip('=')


def _message(msg_id='m1', with_attachment=True):
    parts = [{
        'mimeType': 'multipart/alternative', 'filename': '', 'body': {'size': 0},
        'parts': [
            {'mimeType': 'text/plain', 'filename': '', 'body': {'data': _b64('hello plain')}},
            {'mimeType': 'text/html', 'filename': '', 'body': {'data': _b64('<p>hello</p>')}},
        ],
    }]
    if with_attachment:
        parts.append({'mimeType': 'image/png', 'filename': 'logo.png',
                      'body': {'attachmentId': 'att1', 'size': 3}})
    return {
        'id': msg_id, 'threadId': 't1', 'labelIds': ['INBOX', 'UNREAD'], 'snippet': 'hello',
        'internalDate': '1790000000000',
        'payload': {
            'mimeType': 'multipart/mixed', 'filename': '',
            'headers': [{'name': 'Subject', 'value': 'Hi'}, {'name': 'from', 'value': 'a@x'},
                        {'name': 'To', 'value': 'b@x'}, {'name': 'Message-ID', 'value': '<id@x>'}],
            'parts': parts,
        },
    }


# --- messages.py -------------------------------------------------------


@pytest.mark.parametrize('text', ['a', 'ab', 'abc', 'abcd', 'æøå'])
def test_b64url_decode_handles_missing_padding(text):
    assert messages.b64url_decode(_b64(text)).decode() == text
    assert messages.b64url_decode('') == b''


def test_nested_multipart_bodies_and_attachments():
    out = messages.normalize_message(_message(), with_body=True)
    assert (out['subject'], out['from'], out['message_id']) == ('Hi', 'a@x', '<id@x>')
    assert out['internal_date_ms'] == 1790000000000
    assert out['body_plain'] == 'hello plain' and out['body_html'] == '<p>hello</p>'
    assert out['attachments'] == [
        {'filename': 'logo.png', 'mime_type': 'image/png', 'attachment_id': 'att1', 'size': 3},
    ]
    assert 'body_plain' not in messages.normalize_message(_message())


def test_single_part_message_is_its_own_leaf():
    raw = {'id': 'x', 'payload': {'mimeType': 'text/plain', 'body': {'data': _b64('only')}}}
    assert messages.normalize_message(raw, with_body=True)['body_plain'] == 'only'


def test_text_attachment_is_not_the_body():
    raw = {'id': 'x', 'payload': {'mimeType': 'multipart/mixed', 'parts': [
        {'mimeType': 'text/plain', 'filename': 'notes.txt', 'body': {'data': _b64('file'), 'attachmentId': 'a'}},
        {'mimeType': 'text/plain', 'filename': '', 'body': {'data': _b64('body')}},
    ]}}
    assert messages.normalize_message(raw, with_body=True)['body_plain'] == 'body'


def test_build_list_query():
    q = messages.build_list_query(sender='a@x', to='b@x', subject='hi there', label='inbox',
                                  unread=True, has_attachment=True, since='2026-09-01',
                                  until='2026-09-30', max_results=5, page_token='p')
    assert q == {
        'maxResults': 5, 'pageToken': 'p',
        'q': 'from:a@x to:b@x subject:"hi there" label:inbox is:unread has:attachment '
             'after:2026/09/01 before:2026/09/30',
    }
    assert messages.build_list_query(sender='a@x', search='raw q') == {'maxResults': 25, 'q': 'raw q'}
    assert messages.build_list_query() == {'maxResults': 25}


# --- api.py ------------------------------------------------------------


def test_paginate_follows_next_page_token(monkeypatch):
    pages = [{'messages': [{'id': '1'}], 'nextPageToken': 'p2'},
             {'messages': [{'id': '2'}], 'nextPageToken': 'p3'},
             {'messages': [{'id': '3'}]}]
    seen = []

    def fake_get(base, endpoint, token, params=None, debug=False, retry=0):
        seen.append(params.get('pageToken'))
        return pages[len(seen) - 1]

    monkeypatch.setattr(api, 'api_get', fake_get)
    assert api.paginate(BASE, 'messages', 'tok', {}, 'messages') == ([{'id': '1'}, {'id': '2'}, {'id': '3'}], None)
    assert seen == [None, 'p2', 'p3']
    seen.clear()
    assert api.paginate(BASE, 'messages', 'tok', {}, 'messages', max_pages=1) == ([{'id': '1'}], 'p2')


def test_api_get_builds_url(monkeypatch):
    from types import SimpleNamespace

    seen = {}
    monkeypatch.setattr(api.http, 'request', lambda m, url, **kw: seen.update(url=url) or SimpleNamespace(json={}))
    api.api_get(BASE, '/messages/x', 'tok', params={'format': 'raw'})
    assert seen['url'] == f'{BASE}/messages/x?format=raw'


# --- cli ---------------------------------------------------------------


def _fake_api(monkeypatch, *, next_token=None):
    calls = []

    def fake_paginate(base, endpoint, token, params, key, max_pages=None, debug=False):
        calls.append(('list', params, max_pages))
        return [{'id': 'm1'}], next_token

    def fake_get(base, endpoint, token, params=None, debug=False, retry=0):
        calls.append(('get', endpoint, params))
        if endpoint == 'labels':
            return {'labels': [{'id': 'Label_1', 'name': 'zeta', 'type': 'user'},
                               {'id': 'INBOX', 'name': 'INBOX', 'type': 'system'}]}
        if endpoint.endswith('/attachments/att1'):
            return {'data': _b64('PNG'), 'size': 3}
        if params == {'format': 'raw'}:
            return {'raw': _b64('From: a@x\r\n\r\nbody')}
        return _message()

    monkeypatch.setattr(cli.api_mod, 'paginate', fake_paginate)
    monkeypatch.setattr(cli.api_mod, 'api_get', fake_get)
    return calls


def test_messages_json_and_metadata_fetch(monkeypatch, capsys):
    calls = _fake_api(monkeypatch)
    assert cli.cmd_messages(['--unread', '--max-results', '5'], {}, 'tok', BASE) == 0
    out = capsys.readouterr()
    assert out.err == ''
    rows = json.loads(out.out)
    assert rows[0]['subject'] == 'Hi' and 'body_plain' not in rows[0]
    assert calls[0] == ('list', {'maxResults': 5, 'q': 'is:unread'}, 1)
    assert calls[1] == ('get', 'messages/m1', {'format': 'metadata'})


def test_messages_with_body_all_and_next_page(monkeypatch, capsys):
    calls = _fake_api(monkeypatch, next_token='more')
    assert cli.cmd_messages(['--with-body'], {}, 'tok', BASE) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['next_page_token'] == 'more' and payload['messages'][0]['body_plain'] == 'hello plain'
    assert calls[1][2] == {'format': 'full'}
    _fake_api(monkeypatch)
    assert cli.cmd_messages(['--all', '--pretty'], {}, 'tok', BASE) == 0
    assert 'Hi' in capsys.readouterr().out


@pytest.mark.parametrize('args, match', [
    (['--bogus'], 'Unknown flag'), (['--max-results', 'x'], 'integer'),
    (['--max-results', '0'], 'between'), (['--from'], 'requires a value'),
])
def test_messages_usage_errors(args, match):
    with pytest.raises(UsageError, match=match):
        cli.cmd_messages(args, {}, 'tok', BASE)


def test_show_json_and_pretty(monkeypatch, capsys):
    _fake_api(monkeypatch)
    assert cli.cmd_show(['m1'], {}, 'tok', BASE) == 0
    assert json.loads(capsys.readouterr().out)['attachments'][0]['attachment_id'] == 'att1'
    assert cli.cmd_show(['m1', '--pretty'], {}, 'tok', BASE) == 0
    text = capsys.readouterr().out
    assert 'Subject: Hi' in text and 'Attach:  logo.png' in text and 'hello plain' in text
    with pytest.raises(UsageError, match='expected'):
        cli.cmd_show([], {}, 'tok', BASE)


def test_get_and_attachments_write_exact_bytes(monkeypatch, capsys, tmp_path):
    _fake_api(monkeypatch)
    eml = tmp_path / 'm.eml'
    assert cli.cmd_get(['m1', '--out', str(eml)], {}, 'tok', BASE) == 0
    assert eml.read_bytes() == b'From: a@x\r\n\r\nbody'
    with pytest.raises(ConflictError):
        cli.cmd_get(['m1', '--out', str(eml)], {}, 'tok', BASE)
    assert cli.cmd_get(['m1', '--out', str(eml), '--force'], {}, 'tok', BASE) == 0
    png = tmp_path / 'a.png'
    assert cli.cmd_attachments(['m1', 'att1', '--out', str(png)], {}, 'tok', BASE) == 0
    assert png.read_bytes() == b'PNG'
    capsys.readouterr()
    assert cli.cmd_attachments(['m1', 'att1'], {}, 'tok', BASE) == 0  # stdout bytes path


def test_labels_sorted_system_first(monkeypatch, capsys):
    _fake_api(monkeypatch)
    assert cli.cmd_labels([], {}, 'tok', BASE) == 0
    assert [r['name'] for r in json.loads(capsys.readouterr().out)] == ['INBOX', 'zeta']
    assert cli.cmd_labels(['--pretty'], {}, 'tok', BASE) == 0
    assert 'INBOX' in capsys.readouterr().out


def test_format_empty_states():
    assert format.format_messages_pretty([]) == '(no messages)'
    assert format.format_labels_pretty([]) == '(no labels)'


def test_main_schema_version_and_errors(capsys):
    assert cli._main(['schema']) == 0
    names = {r['name'] for r in json.loads(capsys.readouterr().out)['commands']}
    assert names == {'messages', 'show', 'get', 'attachments', 'labels', 'refresh', 'config'}
    assert cli.main(['--version']) == 0
    assert capsys.readouterr().out.startswith('owa-gmail ')
    assert cli.main(['nope']) == 2
    assert cli.main([]) == 0


def test_main_dispatch_refresh_and_config(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.config_mod, 'config_set', lambda k, v: seen.update({k: v}))
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', lambda config, debug=False: (seen.update(cfg=dict(config)) or 'tok', BASE))
    _fake_api(monkeypatch)
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: {'emailAddress': 'me@x', 'labels': []})
    assert cli._main(['labels', '--profile', 'g1', '--debug']) == 0
    assert seen['cfg'] == {'owa_piggy_profile': 'g1', 'debug': True}
    assert cli._main(['refresh']) == 0
    assert 'Authenticated as me@x' in capsys.readouterr().err
    assert cli._main(['config', '--profile', 'g2']) == 0 and seen['owa_piggy_profile'] == 'g2'
    assert cli._main(['config']) == 0


# --- auth ----------------------------------------------------------------


def test_resolve_profile(monkeypatch):
    g = BrokerProfile('g1', False, True, True, services=['google'])
    nc = BrokerProfile('nc', True, True, True, services=['owa'])
    assert auth.resolve_profile({'owa_piggy_profile': 'x'}) == 'x'
    monkeypatch.setattr(auth, 'get_profiles', lambda **kw: [nc, g])
    assert auth.resolve_profile({}) == 'g1'
    monkeypatch.setattr(auth, 'get_profiles', lambda **kw: [nc])
    with pytest.raises(UsageError, match='setup'):
        auth.resolve_profile({})
    g2 = BrokerProfile('g2', False, True, True, services=['google'])
    monkeypatch.setattr(auth, 'get_profiles', lambda **kw: [g, g2])
    with pytest.raises(UsageError, match='g1, g2'):
        auth.resolve_profile({})


def test_setup_auth_maps_aad_profile_and_passes_other_errors(monkeypatch):
    monkeypatch.setattr(auth, 'get_token', lambda **kw: BrokerToken('opaque', 'gmail'))
    assert auth.setup_auth({'owa_piggy_profile': 'g1'}) == ('opaque', auth.API_BASE)

    def unknown(**kw):
        raise AuthExpiredError("unknown audience 'gmail'")

    monkeypatch.setattr(auth, 'get_token', unknown)
    with pytest.raises(UsageError, match='not a Google profile'):
        auth.setup_auth({'owa_piggy_profile': 'nc'})

    def expired(**kw):
        raise AuthExpiredError('invalid_grant')

    monkeypatch.setattr(auth, 'get_token', expired)
    with pytest.raises(AuthExpiredError):
        auth.setup_auth({'owa_piggy_profile': 'g1'})
