"""CLI flag validation: each cmd_* parses its flags correctly and
fails fast on missing-required / mutually-exclusive combinations.

We patch api_mod.api_request (or api_get) where needed so commands
don't reach the network. The point is to lock the dispatch / flag
loop semantics, not to retest the API helper.
"""
import json
import sys

import pytest


def _fake_token():
    return 'fake-access', 'https://outlook.office.com/api/v2.0'


# ----- messages -----

def test_messages_search_with_filter_is_rejected(monkeypatch, capsys):
    from owa_mail.cli import cmd_messages
    rc = cmd_messages(['--search', 'hi', '--unread'], {}, *_fake_token())
    assert rc == 1
    err = capsys.readouterr().err
    assert '$search' in err and '$filter' in err


def test_messages_unknown_flag_exits(monkeypatch):
    from owa_mail.cli import cmd_messages
    with pytest.raises(SystemExit):
        cmd_messages(['--bogus'], {}, *_fake_token())


def test_messages_passes_filter_and_orderby(monkeypatch, capsys):
    """When called with --unread --since, the OData query must include
    $filter, the right $orderby, and our $select."""
    from owa_mail import api as api_mod
    from owa_mail.cli import cmd_messages

    captured = {}

    def fake_get(base, endpoint, token, debug=False):
        captured['endpoint'] = endpoint
        return {'value': []}

    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    rc = cmd_messages(
        ['--unread', '--since', '2026-04-01', '--limit', '10'],
        {}, *_fake_token(),
    )
    assert rc == 0
    ep = captured['endpoint']
    assert 'me/MailFolders/Inbox/messages' in ep
    assert '%24filter' in ep or '$filter' in ep
    assert '%24orderby' in ep or '$orderby' in ep
    assert 'IsRead' in ep.replace('%20', ' ') or 'IsRead' in ep
    # JSON on stdout (empty list)
    out = capsys.readouterr().out.strip()
    assert out == '[]'


def test_messages_subject_filter_omits_orderby(monkeypatch, capsys):
    from owa_mail import api as api_mod
    from owa_mail.cli import cmd_messages

    captured = {}

    def fake_get(base, endpoint, token, debug=False):
        captured['endpoint'] = endpoint
        return {'value': []}

    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    rc = cmd_messages(['--subject', 'invoice'], {}, *_fake_token())
    assert rc == 0
    ep = captured['endpoint']
    assert '%24filter' in ep or '$filter' in ep
    assert 'contains%28Subject' in ep or "contains(Subject" in ep
    assert '%24orderby' not in ep and '$orderby' not in ep
    assert capsys.readouterr().out.strip() == '[]'


def test_messages_from_filter_omits_orderby(monkeypatch, capsys):
    from owa_mail import api as api_mod
    from owa_mail.cli import cmd_messages

    captured = {}

    def fake_get(base, endpoint, token, debug=False):
        captured['endpoint'] = endpoint
        return {'value': []}

    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    rc = cmd_messages(['--from', 'alice@example.com'], {}, *_fake_token())
    assert rc == 0
    ep = captured['endpoint']
    assert '%24filter' in ep or '$filter' in ep
    assert 'From%2FEmailAddress%2FAddress' in ep or 'From/EmailAddress/Address' in ep
    assert '%24orderby' not in ep and '$orderby' not in ep
    assert capsys.readouterr().out.strip() == '[]'


# ----- show -----

def test_show_requires_id(capsys):
    from owa_mail.cli import cmd_show
    rc = cmd_show([], {}, *_fake_token())
    assert rc == 1
    assert '--id is required' in capsys.readouterr().err


# ----- send -----

def test_send_requires_to(capsys):
    from owa_mail.cli import cmd_send
    rc = cmd_send(['--subject', 's', '--body', 'b'], {}, *_fake_token())
    assert rc == 1
    assert '--to is required' in capsys.readouterr().err


def test_send_requires_subject(capsys):
    from owa_mail.cli import cmd_send
    rc = cmd_send(['--to', 'a@b.c', '--body', 'b'], {}, *_fake_token())
    assert rc == 1
    assert '--subject is required' in capsys.readouterr().err


def test_send_immediate_path_calls_sendmail(monkeypatch, capsys):
    from owa_mail import api as api_mod
    from owa_mail.cli import cmd_send

    calls = []

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        calls.append((method, endpoint, body))
        return {}

    monkeypatch.setattr(api_mod, 'api_request', fake_request)
    rc = cmd_send(
        ['--to', 'a@b.c', '--subject', 'hi', '--body', 'hello'],
        {}, *_fake_token(),
    )
    assert rc == 0
    assert len(calls) == 1
    method, endpoint, body = calls[0]
    assert method == 'POST'
    assert endpoint == 'me/sendMail'
    assert body['Message']['Subject'] == 'hi'
    assert body['SaveToSentItems'] is True


def test_send_save_draft_path_creates_message_only(monkeypatch):
    from owa_mail import api as api_mod
    from owa_mail.cli import cmd_send

    calls = []

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        calls.append((method, endpoint))
        if endpoint == 'me/messages':
            return {'Id': 'DRAFT1', 'Subject': 'hi'}
        return {}

    monkeypatch.setattr(api_mod, 'api_request', fake_request)
    rc = cmd_send(
        ['--to', 'a@b.c', '--subject', 'hi', '--body', 'b', '--save-draft'],
        {}, *_fake_token(),
    )
    assert rc == 0
    assert calls == [('POST', 'me/messages')]


def test_send_with_send_at_creates_draft_then_sends(monkeypatch):
    from owa_mail import api as api_mod
    from owa_mail.cli import cmd_send

    calls = []
    seen_body = {}

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        calls.append((method, endpoint))
        if endpoint == 'me/messages':
            seen_body['draft'] = body
            return {'Id': 'DRAFT1', 'Subject': 'hi'}
        return {}

    monkeypatch.setattr(api_mod, 'api_request', fake_request)
    rc = cmd_send(
        ['--to', 'a@b.c', '--subject', 'hi', '--body', 'b',
         '--send-at', '2026-05-01T09:00:00Z'],
        {}, *_fake_token(),
    )
    assert rc == 0
    assert calls == [('POST', 'me/messages'), ('POST', 'me/messages/DRAFT1/send')]
    props = seen_body['draft']['SingleValueExtendedProperties']
    assert props[0]['PropertyId'] == 'SystemTime 0x3FEF'


# ----- delete -----

def test_delete_requires_id(capsys):
    from owa_mail.cli import cmd_delete
    rc = cmd_delete([], {}, *_fake_token())
    assert rc == 1


# ----- move -----

def test_move_requires_id_and_to(capsys):
    from owa_mail.cli import cmd_move
    rc = cmd_move(['--id', 'X'], {}, *_fake_token())
    assert rc == 1
    assert '--to is required' in capsys.readouterr().err


def test_move_resolves_well_known_destination(monkeypatch):
    from owa_mail import api as api_mod
    from owa_mail.cli import cmd_move

    seen = {}

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        seen['body'] = body
        seen['endpoint'] = endpoint
        return {'Id': 'X', 'Subject': 's'}

    monkeypatch.setattr(api_mod, 'api_request', fake_request)
    rc = cmd_move(['--id', 'X', '--to', 'archive'], {}, *_fake_token())
    assert rc == 0
    assert seen['body']['DestinationId'] == 'Archive'
    assert '/move' in seen['endpoint']


# ----- mark -----

def test_mark_requires_id_and_action(capsys):
    from owa_mail.cli import cmd_mark
    rc = cmd_mark(['--id', 'X'], {}, *_fake_token())
    assert rc == 1
    assert 'requires one of' in capsys.readouterr().err


def test_mark_read_and_unread_mutually_exclusive(capsys):
    from owa_mail.cli import cmd_mark
    rc = cmd_mark(['--id', 'X', '--read', '--unread'], {}, *_fake_token())
    assert rc == 1
    assert 'mutually exclusive' in capsys.readouterr().err


def test_mark_flag_and_unflag_mutually_exclusive(capsys):
    from owa_mail.cli import cmd_mark
    rc = cmd_mark(['--id', 'X', '--flag', '--unflag'], {}, *_fake_token())
    assert rc == 1
    assert 'mutually exclusive' in capsys.readouterr().err


def test_mark_read_emits_patch(monkeypatch):
    from owa_mail import api as api_mod
    from owa_mail.cli import cmd_mark

    seen = {}

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        seen['method'] = method
        seen['body'] = body
        return {'Id': 'X'}

    monkeypatch.setattr(api_mod, 'api_request', fake_request)
    rc = cmd_mark(['--id', 'X', '--read'], {}, *_fake_token())
    assert rc == 0
    assert seen['method'] == 'PATCH'
    assert seen['body'] == {'IsRead': True}


# ----- reply / forward -----

def test_reply_requires_id():
    from owa_mail.cli import cmd_reply
    rc = cmd_reply(['--body', 'hi'], {}, *_fake_token())
    assert rc == 1


def test_reply_requires_body_or_save_draft(capsys):
    from owa_mail.cli import cmd_reply
    rc = cmd_reply(['--id', 'X'], {}, *_fake_token())
    assert rc == 1
    assert '--body is required' in capsys.readouterr().err


def test_reply_save_draft_without_body_skips_patch(monkeypatch):
    from owa_mail import api as api_mod
    from owa_mail.cli import cmd_reply

    calls = []

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        calls.append((method, endpoint, body))
        if endpoint.endswith('/createReply'):
            return {'Id': 'DRAFT1'}
        raise AssertionError(f'unexpected request: {method} {endpoint}')

    def fake_get(base, endpoint, token, debug=False):
        calls.append(('GET', endpoint, None))
        return {'Id': 'DRAFT1', 'Subject': 'hi'}

    monkeypatch.setattr(api_mod, 'api_request', fake_request)
    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    rc = cmd_reply(['--id', 'X', '--save-draft'], {}, *_fake_token())
    assert rc == 0
    assert calls == [
        ('POST', 'me/messages/X/createReply', None),
        ('GET', 'me/messages/DRAFT1?$select=Id%2CConversationId%2CReceivedDateTime%2CSubject%2CFrom%2CToRecipients%2CCcRecipients%2CBccRecipients%2CBodyPreview%2CIsRead%2CHasAttachments%2CImportance%2CFlag%2CWebLink%2CParentFolderId', None),
    ]


def test_forward_requires_to_when_sending(capsys):
    from owa_mail.cli import cmd_forward
    rc = cmd_forward(['--id', 'X', '--body', 'fyi'], {}, *_fake_token())
    assert rc == 1
    assert '--to' in capsys.readouterr().err


def test_forward_rejects_cc(monkeypatch):
    from owa_mail.cli import cmd_forward
    with pytest.raises(SystemExit):
        cmd_forward(['--id', 'X', '--to', 'a@b.c', '--cc', 'c@d.e', '--body', 'fyi'], {}, *_fake_token())


def test_reply_rejects_importance(monkeypatch):
    from owa_mail.cli import cmd_reply
    with pytest.raises(SystemExit):
        cmd_reply(['--id', 'X', '--body', 'hi', '--importance', 'high'], {}, *_fake_token())


def test_reply_full_flow(monkeypatch):
    from owa_mail import api as api_mod
    from owa_mail.cli import cmd_reply

    calls = []

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        calls.append((method, endpoint))
        if endpoint.endswith('/createReply'):
            return {'Id': 'DRAFT1'}
        return {}

    monkeypatch.setattr(api_mod, 'api_request', fake_request)
    rc = cmd_reply(['--id', 'X', '--body', 'thanks'], {}, *_fake_token())
    assert rc == 0
    assert calls == [
        ('POST', 'me/messages/X/createReply'),
        ('PATCH', 'me/messages/DRAFT1'),
        ('POST', 'me/messages/DRAFT1/send'),
    ]


# ----- folders -----

def test_folders_pretty(monkeypatch, capsys):
    from owa_mail import api as api_mod
    from owa_mail.cli import cmd_folders

    def fake_get(base, endpoint, token, debug=False):
        return {'value': [{'Id': '1', 'DisplayName': 'Inbox', 'UnreadItemCount': 3, 'TotalItemCount': 30}]}

    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    rc = cmd_folders(['--pretty'], {}, *_fake_token())
    assert rc == 0
    out = capsys.readouterr().out
    assert 'Inbox' in out
    assert 'unread=3' in out


def test_folders_json(monkeypatch, capsys):
    from owa_mail import api as api_mod
    from owa_mail.cli import cmd_folders

    def fake_get(base, endpoint, token, debug=False):
        return {'value': [{'Id': '1', 'DisplayName': 'Inbox', 'UnreadItemCount': 0, 'TotalItemCount': 0}]}

    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    rc = cmd_folders([], {}, *_fake_token())
    assert rc == 0
    items = json.loads(capsys.readouterr().out)
    assert items == [{'id': '1', 'name': 'Inbox', 'unread': 0, 'total': 0}]
