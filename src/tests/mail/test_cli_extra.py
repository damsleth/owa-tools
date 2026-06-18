"""Extra CLI coverage tests for owa_mail.cli and owa_mail.dates.

Targets the Missing line ranges reported by coverage:
  cli.py:  83-227, 232, 240-241, 284, 286, 321, 323, 335, 351, 363-366,
           396, 400, 402, 406, 408, 518-519, 646-647, 654, 681, 719, 723,
           749, 753, 770, 797, 813, 815->822, 841, 843, 868, 873, 876,
           881-883, 885, 896, 911, 921, 924, 947, 958, 978->980,
           1158-1159, 1161-1162, 1164-1165, 1169, 1172-1173, 1181, 1193, 1197
  dates.py: 10, 14, 18, 25, 27, 29 (resolve_date helpers)
"""
import json

import pytest

from owa_mail import cli
from owa_mail.dates import resolve_date, today, tomorrow, yesterday

# ---------------------------------------------------------------------------
# dates.py coverage (lines 10, 14, 18, 25, 27, 29)
# ---------------------------------------------------------------------------

def test_today_returns_iso_string():
    import re
    result = today()
    assert re.match(r'^\d{4}-\d{2}-\d{2}$', result)


def test_tomorrow_is_one_day_after_today():
    from datetime import date, timedelta
    expected = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    assert tomorrow() == expected


def test_yesterday_is_one_day_before_today():
    from datetime import date, timedelta
    expected = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    assert yesterday() == expected


def test_resolve_date_today():
    result = resolve_date('today')
    assert result == today()


def test_resolve_date_tomorrow():
    result = resolve_date('tomorrow')
    assert result == tomorrow()


def test_resolve_date_yesterday():
    result = resolve_date('yesterday')
    assert result == yesterday()


def test_resolve_date_passthrough():
    assert resolve_date('2026-05-01') == '2026-05-01'
    assert resolve_date('') == ''


# ---------------------------------------------------------------------------
# Fixtures shared across cli tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', lambda config, debug=False: ('tok', 'https://outlook.test'))


def _raw_message(msg_id='m1', subject='Hello'):
    return {
        'Id': msg_id,
        'ConversationId': 'c1',
        'ReceivedDateTime': '2026-05-09T10:00:00Z',
        'SentDateTime': '2026-05-09T09:59:00Z',
        'Subject': subject,
        'From': {'EmailAddress': {'Address': 'ada@example.com'}},
        'ToRecipients': [{'EmailAddress': {'Address': 'bob@example.com'}}],
        'BodyPreview': 'preview',
        'Body': {'ContentType': 'Text', 'Content': 'body text'},
        'IsRead': False,
        'HasAttachments': False,
        'Importance': 'Normal',
        'Flag': {'FlagStatus': 'NotFlagged'},
        'ParentFolderId': 'inbox',
    }


# ---------------------------------------------------------------------------
# print_help (lines 83-227)
# ---------------------------------------------------------------------------

def test_print_help_contains_commands(capsys):
    cli.print_help()
    out = capsys.readouterr().out
    assert 'owa-mail' in out
    assert 'messages' in out
    assert 'send' in out
    assert 'reply' in out
    assert 'folders' in out


# ---------------------------------------------------------------------------
# _require_value raises UsageError when args is empty (line 232)
# ---------------------------------------------------------------------------

def test_require_value_raises_on_empty():
    with pytest.raises(cli.UsageError, match='requires a value'):
        cli._require_value('--foo', [])


# ---------------------------------------------------------------------------
# _require_int raises UsageError on non-integer (lines 240-241)
# ---------------------------------------------------------------------------

def test_require_int_raises_on_non_integer():
    with pytest.raises(cli.UsageError, match='requires an integer'):
        cli._require_int('--limit', ['abc'])


# ---------------------------------------------------------------------------
# cmd_messages: --with-body (line 284), --pretty (line 286)
# --all pagination with pretty print (321, 323)
# --all pagination with json + search sort (321)
# pretty non-paginated (335)
# ---------------------------------------------------------------------------

def test_messages_with_body_flag(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: {'value': [_raw_message()]})
    rc = cli.cmd_messages(['--with-body'], {}, 'tok', 'https://outlook.test')
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]['body'] == 'body text'


def test_messages_pretty_flag(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: {'value': [_raw_message()]})
    rc = cli.cmd_messages(['--pretty'], {}, 'tok', 'https://outlook.test')
    assert rc == 0
    assert 'Hello' in capsys.readouterr().out


def test_messages_all_pages_json(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'paginate_all', lambda *a, **k: [_raw_message()])
    rc = cli.cmd_messages(['--all'], {}, 'tok', 'https://outlook.test')
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]['subject'] == 'Hello'


def test_messages_all_pages_pretty(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'paginate_all', lambda *a, **k: [_raw_message()])
    rc = cli.cmd_messages(['--all', '--pretty'], {}, 'tok', 'https://outlook.test')
    assert rc == 0
    assert 'Hello' in capsys.readouterr().out


def test_messages_all_pages_search_sorts_newest_first(monkeypatch, capsys):
    items = [
        {**_raw_message('old', 'Old'), 'ReceivedDateTime': '2026-05-01T10:00:00Z'},
        {**_raw_message('new', 'New'), 'ReceivedDateTime': '2026-05-09T10:00:00Z'},
    ]
    monkeypatch.setattr(cli.api_mod, 'paginate_all', lambda *a, **k: items)
    rc = cli.cmd_messages(['--all', '--search', 'budget'], {}, 'tok', 'https://outlook.test')
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]['id'] == 'new'


def test_messages_all_pages_api_failure(monkeypatch):
    monkeypatch.setattr(cli.api_mod, 'paginate_all', lambda *a, **k: None)
    assert cli.cmd_messages(['--all'], {}, 'tok', 'https://outlook.test') == 1


# ---------------------------------------------------------------------------
# cmd_show: unknown flag (line 351), AAQk id hint (lines 363-366)
# ---------------------------------------------------------------------------

def test_show_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli.cmd_show(['--bogus'], {}, 'tok', 'https://outlook.test')


def test_show_aaqk_id_hint(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: None)
    rc = cli.cmd_show(['--id', 'AAQkXXXX'], {}, 'tok', 'https://outlook.test')
    assert rc == 1
    err = capsys.readouterr().err
    assert 'conversation_id' in err.lower() or 'conversation' in err


def test_show_api_failure_non_aaqk(monkeypatch):
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: None)
    # Regular AQMk id — no hint, just return 1
    rc = cli.cmd_show(['--id', 'AQMkRegularId'], {}, 'tok', 'https://outlook.test')
    assert rc == 1


# ---------------------------------------------------------------------------
# cmd_read: --folder (396), --from (400), --subject (402), --since (406), --until (408)
# ---------------------------------------------------------------------------

def test_read_with_all_filters(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: {'value': [_raw_message()]})
    rc = cli.cmd_read([
        '--folder', 'SentItems',
        '--unread',
        '--from', 'ada',
        '--subject', 'hello',
        '--since', 'yesterday',
        '--until', 'today',
        '--pretty',
    ], {}, 'tok', 'https://outlook.test')
    assert rc == 0
    assert 'Hello' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_attachment_get: write failure (lines 518-519)
# ---------------------------------------------------------------------------

def test_attachment_get_write_failure(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli.api_mod, 'api_get_binary', lambda *a, **k: b'data')
    bad_path = str(tmp_path / 'nonexistent_dir' / 'file.bin')
    rc = cli.cmd_attachment_get(
        ['--id', 'm1', '--attachment', 'a1', '--out', bad_path],
        {}, 'tok', 'https://outlook.test',
    )
    assert rc == 1
    assert 'cannot write' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cmd_send: ValueError from build_draft_payload (646-647), draft api failure (654),
# send draft failure (681)
# ---------------------------------------------------------------------------

def test_send_draft_invalid_send_at_raises(monkeypatch):
    """build_draft_payload raises ValueError on bad --send-at → UsageError."""
    def fake_request(method, api_base, endpoint, access_token, **kwargs):
        if endpoint == 'me/messages':
            return _raw_message('draft-1', 'Draft')
        return {}

    monkeypatch.setattr(cli.api_mod, 'api_request', fake_request)

    import owa_mail.messages as messages_mod
    original = messages_mod.build_draft_payload

    def bad_draft(msg, send_at=None):
        if send_at:
            raise ValueError('invalid send_at format')
        return original(msg, send_at=send_at)

    monkeypatch.setattr(messages_mod, 'build_draft_payload', bad_draft)

    with pytest.raises(cli.UsageError, match='invalid send_at format'):
        cli.cmd_send(
            ['--to', 'bob@example.com', '--subject', 'Later',
             '--send-at', 'bad-date'],
            {}, 'tok', 'https://outlook.test',
        )


def test_send_draft_creation_api_failure(monkeypatch):
    """api_request returns None for draft creation → return 1."""
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: None)
    rc = cli.cmd_send(
        ['--to', 'bob@example.com', '--subject', 'Hi', '--send-at', '2026-05-01T09:00:00Z'],
        {}, 'tok', 'https://outlook.test',
    )
    assert rc == 1


def test_send_send_draft_api_failure(monkeypatch):
    """POST /send returns None → return 1."""
    call_count = [0]

    def fake_request(method, api_base, endpoint, access_token, **kwargs):
        call_count[0] += 1
        if endpoint == 'me/messages':
            return _raw_message('draft-x', 'Draft')
        # The /send call fails
        return None

    monkeypatch.setattr(cli.api_mod, 'api_request', fake_request)
    rc = cli.cmd_send(
        ['--to', 'bob@example.com', '--subject', 'Hi', '--send-at', '2026-05-01T09:00:00Z'],
        {}, 'tok', 'https://outlook.test',
    )
    assert rc == 1


# ---------------------------------------------------------------------------
# _reply_like: createReply draft fails (719), no draft id (723),
# small attachment POST fails (749), large upload fails (753), send fails (770)
# ---------------------------------------------------------------------------

def test_reply_draft_creation_fails(monkeypatch):
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: None)
    assert cli.cmd_reply(['--id', 'm1', '--body', 'hi'], {}, 'tok', 'https://outlook.test') == 1


def test_reply_no_draft_id_returned(monkeypatch):
    """createReply returns a message without an Id field → return 1."""
    def fake_request(method, api_base, endpoint, access_token, **kwargs):
        if 'createReply' in endpoint:
            return {}  # normalize_message → id=''
        return {}

    monkeypatch.setattr(cli.api_mod, 'api_request', fake_request)
    rc = cli.cmd_reply(['--id', 'm1', '--body', 'hi'], {}, 'tok', 'https://outlook.test')
    assert rc == 1


def test_reply_small_attachment_post_fails(monkeypatch, tmp_path):
    """Inline (small) attachment POST fails → return 1."""
    attach_file = tmp_path / 'note.txt'
    attach_file.write_bytes(b'hello')

    def fake_request(method, api_base, endpoint, access_token, **kwargs):
        if 'createReply' in endpoint:
            return _raw_message('draft-1', 'Draft')
        if method == 'PATCH':
            return _raw_message('draft-1', 'Patched')
        # The attachment POST fails
        return None

    monkeypatch.setattr(cli.api_mod, 'api_request', fake_request)
    rc = cli.cmd_reply(
        ['--id', 'm1', '--body', 'hi', '--attach', str(attach_file)],
        {}, 'tok', 'https://outlook.test',
    )
    assert rc == 1


def test_reply_send_fails(monkeypatch):
    """PATCH succeeds but final /send returns None → return 1."""
    def fake_request(method, api_base, endpoint, access_token, **kwargs):
        if 'createReply' in endpoint:
            return _raw_message('draft-1', 'Draft')
        if method == 'PATCH':
            return _raw_message('draft-1', 'Patched')
        # /send fails
        return None

    monkeypatch.setattr(cli.api_mod, 'api_request', fake_request)
    rc = cli.cmd_reply(['--id', 'm1', '--body', 'hi'], {}, 'tok', 'https://outlook.test')
    assert rc == 1


# ---------------------------------------------------------------------------
# cmd_delete: unknown flag (797), get existing fails (813), confirm=False aborts (815->822)
# ---------------------------------------------------------------------------

def test_delete_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli.cmd_delete(['--id', 'm1', '--bogus'], {}, 'tok', 'https://outlook.test')


def test_delete_get_existing_fails(monkeypatch):
    monkeypatch.setattr(cli.tty_mod, 'require_confirm_or_tty', lambda action: None)
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: None)
    rc = cli.cmd_delete(['--id', 'm1'], {}, 'tok', 'https://outlook.test')
    assert rc == 1


# ---------------------------------------------------------------------------
# cmd_move: unknown flag (841), missing --to (843)
# ---------------------------------------------------------------------------

def test_move_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli.cmd_move(['--id', 'm1', '--bogus'], {}, 'tok', 'https://outlook.test')


def test_move_missing_to_raises():
    with pytest.raises(cli.UsageError, match='--to is required'):
        cli.cmd_move(['--id', 'm1'], {}, 'tok', 'https://outlook.test')


# ---------------------------------------------------------------------------
# cmd_mark: flag_state True → --unflag raises (868), --flag → read is False (873),
# flag_state False → --flag raises (876), flag_state False branches (881-883, 885, 896)
# ---------------------------------------------------------------------------

def test_mark_unflag_after_flag_raises():
    with pytest.raises(cli.UsageError, match='mutually exclusive'):
        cli.cmd_mark(['--id', 'm1', '--flag', '--unflag'], {}, 'tok', 'https://outlook.test')


def test_mark_flag_after_unflag_raises():
    with pytest.raises(cli.UsageError, match='mutually exclusive'):
        cli.cmd_mark(['--id', 'm1', '--unflag', '--flag'], {}, 'tok', 'https://outlook.test')


def test_mark_read_then_unread_raises():
    with pytest.raises(cli.UsageError, match='mutually exclusive'):
        cli.cmd_mark(['--id', 'm1', '--read', '--unread'], {}, 'tok', 'https://outlook.test')


def test_mark_unread_then_read_raises():
    with pytest.raises(cli.UsageError, match='mutually exclusive'):
        cli.cmd_mark(['--id', 'm1', '--unread', '--read'], {}, 'tok', 'https://outlook.test')


def test_mark_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli.cmd_mark(['--id', 'm1', '--read', '--bogus'], {}, 'tok', 'https://outlook.test')


def test_mark_missing_id_raises():
    with pytest.raises(cli.UsageError, match='--id is required'):
        cli.cmd_mark(['--read'], {}, 'tok', 'https://outlook.test')


def test_mark_api_failure(monkeypatch):
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: None)
    rc = cli.cmd_mark(['--id', 'm1', '--unflag'], {}, 'tok', 'https://outlook.test')
    assert rc == 1


def test_mark_unflag_success(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: _raw_message('m1', 'Test'))
    rc = cli.cmd_mark(['--id', 'm1', '--unflag'], {}, 'tok', 'https://outlook.test')
    assert rc == 0
    assert json.loads(capsys.readouterr().out)['id'] == 'm1'


# ---------------------------------------------------------------------------
# cmd_folders: unknown flag (911), --all pagination failure (921), --all pretty (924)
# ---------------------------------------------------------------------------

def test_folders_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli.cmd_folders(['--bogus'], {}, 'tok', 'https://outlook.test')


def test_folders_all_pages_api_failure(monkeypatch):
    monkeypatch.setattr(cli.api_mod, 'paginate_all', lambda *a, **k: None)
    rc = cli.cmd_folders(['--all'], {}, 'tok', 'https://outlook.test')
    assert rc == 1


def test_folders_all_pages_pretty(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'paginate_all', lambda *a, **k: [
        {'Id': 'f1', 'DisplayName': 'Inbox', 'UnreadItemCount': 1, 'TotalItemCount': 5}
    ])
    rc = cli.cmd_folders(['--all', '--pretty'], {}, 'tok', 'https://outlook.test')
    assert rc == 0
    assert 'Inbox' in capsys.readouterr().out


def test_folders_all_pages_json(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'paginate_all', lambda *a, **k: [
        {'Id': 'f1', 'DisplayName': 'Inbox', 'UnreadItemCount': 1, 'TotalItemCount': 5}
    ])
    rc = cli.cmd_folders(['--all'], {}, 'tok', 'https://outlook.test')
    assert rc == 0
    folders = json.loads(capsys.readouterr().out)
    assert folders[0]['name'] == 'Inbox'


# ---------------------------------------------------------------------------
# cmd_config: unknown flag (947), no profile set message (958)
# ---------------------------------------------------------------------------

def test_config_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli.cmd_config(['--bogus'], {})


def test_config_no_profile_set_message(capsys):
    rc = cli.cmd_config([], {})
    assert rc == 0
    assert 'not set' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cmd_refresh: name absent from me dict (978->980)
# ---------------------------------------------------------------------------

def test_refresh_no_display_name(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, 'do_token_refresh', lambda config, debug=False: 'tok')
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: {})  # no DisplayName key
    rc = cli.cmd_refresh([], {})
    assert rc == 0
    err = capsys.readouterr().err
    # Should not print "Authenticated as" since name is falsy
    assert 'Authenticated as' not in err


# ---------------------------------------------------------------------------
# _main: empty argv (1158-1159), -h flag (1161-1162), --version/-v (1163-1165),
# UsageError from _split_globals (1169), empty argv after split (1172-1173),
# subcommand help (1181), refresh dispatch (1193), unknown command (1197)
# ---------------------------------------------------------------------------

def test_main_empty_argv(capsys):
    rc = cli._main([])
    assert rc == 0
    assert 'owa-mail' in capsys.readouterr().out


def test_main_dash_h(capsys):
    rc = cli._main(['-h'])
    assert rc == 0
    assert 'owa-mail' in capsys.readouterr().out


def test_main_help_command(capsys):
    rc = cli._main(['help'])
    assert rc == 0
    assert 'owa-mail' in capsys.readouterr().out


def test_main_version_flag(capsys):
    rc = cli._main(['--version'])
    assert rc == 0
    assert 'owa-mail' in capsys.readouterr().out


def test_main_v_flag(capsys):
    rc = cli._main(['-v'])
    assert rc == 0
    assert 'owa-mail' in capsys.readouterr().out


def test_main_split_globals_error():
    with pytest.raises(cli.UsageError, match='requires a value'):
        cli._main(['--profile'])


def test_main_empty_after_global_flags(capsys):
    """--debug with no subcommand → help."""
    rc = cli._main(['--debug'])
    assert rc == 0
    assert 'owa-mail' in capsys.readouterr().out


def test_main_subcommand_help(capsys):
    rc = cli._main(['messages', '--help'])
    assert rc == 0


def test_main_refresh_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, 'do_token_refresh', lambda config, debug=False: 'tok')
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: {'DisplayName': 'Ada'})
    rc = cli._main(['refresh'])
    assert rc == 0
    assert 'Ada' in capsys.readouterr().err


def test_main_unknown_command():
    with pytest.raises(cli.UsageError, match='Unknown command'):
        cli._main(['frobnicate'])
