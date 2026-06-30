"""End-to-end `_main` dispatch + global-flag tests for owa-teams. No network."""

import json

import pytest

from owa_teams import cli


@pytest.fixture
def stub_graph(monkeypatch):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.auth_mod, 'graph_setup',
                        lambda config, debug=False: ('tok', 'https://g/v1.0'))


@pytest.fixture
def stub_chatsvc(monkeypatch):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.auth_mod, 'chatsvc_setup',
                        lambda config, debug=False, region=None: ('tok', 'https://t/api/chatsvc/emea/v1'))


# --- routing ------------------------------------------------------------------

def test_main_routes_teams(monkeypatch, capsys, stub_graph):
    monkeypatch.setattr(cli.api_mod, 'graph_get',
                        lambda base, ep, tok, **k: {'value': [{'id': 't1', 'displayName': 'A'}]})
    assert cli._main(['teams']) == 0
    assert json.loads(capsys.readouterr().out)[0]['id'] == 't1'


def test_main_teams_alias_ls(monkeypatch, capsys, stub_graph):
    monkeypatch.setattr(cli.api_mod, 'graph_get', lambda base, ep, tok, **k: {'value': []})
    assert cli._main(['ls']) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_main_routes_channels_positional_team(monkeypatch, capsys, stub_graph):
    seen = {}
    monkeypatch.setattr(cli.api_mod, 'graph_collect',
                        lambda base, ep, tok, **k: seen.update(ep=ep) or ([{'id': 'c1', 'displayName': 'Gen'}], False))
    assert cli._main(['channels', 'TEAM-1']) == 0
    assert 'teams/TEAM-1/channels' in seen['ep']
    assert json.loads(capsys.readouterr().out)[0]['id'] == 'c1'


def test_main_channels_requires_team(stub_graph):
    with pytest.raises(cli.UsageError, match='requires --team'):
        cli._main(['channels'])


def test_main_routes_chats_with_type_filter(monkeypatch, capsys, stub_graph):
    monkeypatch.setattr(cli.api_mod, 'graph_collect', lambda base, ep, tok, **k: ([
        {'id': 'a', 'chatType': 'oneOnOne'}, {'id': 'b', 'chatType': 'meeting'},
    ], False))
    assert cli._main(['chats', '--type', 'meeting']) == 0
    out = json.loads(capsys.readouterr().out)
    assert [c['id'] for c in out] == ['b']


def test_main_routes_messages_channel(monkeypatch, capsys, stub_chatsvc):
    # chatsvc returns newest-first; the normalizer reverses to chronological.
    raw = [
        {'id': '9', 'rootMessageId': '8', 'sequenceId': 9, 'messagetype': 'Text',
         'content': 'reply', 'imdisplayname': 'L', 'from': 'x/contacts/8:orgid:L',
         'properties': {}, 'originalarrivaltime': 't2'},
        {'id': '8', 'rootMessageId': '8', 'sequenceId': 8, 'messagetype': 'Text',
         'content': 'root', 'imdisplayname': 'D', 'from': 'x/contacts/8:orgid:D',
         'properties': {'subject': 'S'}, 'originalarrivaltime': 't1'},
    ]
    seen = {}
    monkeypatch.setattr(cli.api_mod, 'chatsvc_messages',
                        lambda base, cid, tok, **k: seen.update(cid=cid, k=k) or raw)
    assert cli._main(['messages', '--channel', '19:c@thread.tacv2', '--team', 'T', '--limit', '2']) == 0
    out = json.loads(capsys.readouterr().out)
    assert seen['cid'] == '19:c@thread.tacv2'
    assert seen['k']['max_pages'] == 2
    assert out[1]['isReply'] is True
    assert out[1]['threadId'] == '19:c@thread.tacv2:8'


def test_main_messages_since_forwarded(monkeypatch, capsys, stub_chatsvc):
    seen = {}
    monkeypatch.setattr(cli.api_mod, 'chatsvc_messages',
                        lambda base, cid, tok, **k: seen.update(k=k) or [])
    assert cli._main(['messages', '--chat', '19:x@unq.gbl.spaces', '--since', '2026-06-01']) == 0
    assert seen['k']['since_dt'] is not None
    capsys.readouterr()


def test_main_messages_since_invalid_is_usage_error(stub_chatsvc):
    with pytest.raises(cli.UsageError, match='ISO-8601'):
        cli._main(['messages', '--chat', 'c', '--since', 'notadate'])


def test_main_messages_region_override_forwarded(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.auth_mod, 'chatsvc_setup',
                        lambda config, debug=False, region=None:
                        seen.update(region=region) or ('tok', 'https://t/api/chatsvc/amer/v1'))
    monkeypatch.setattr(cli.api_mod, 'chatsvc_messages', lambda base, cid, tok, **k: [])
    assert cli._main(['messages', '--chat', '19:x@unq.gbl.spaces', '--region', 'amer']) == 0
    assert seen['region'] == 'amer'
    capsys.readouterr()


def test_main_routes_messages_chat_is_flat(monkeypatch, capsys, stub_chatsvc):
    monkeypatch.setattr(cli.api_mod, 'chatsvc_messages', lambda base, cid, tok, **k: [
        {'id': '1', 'messagetype': 'Text', 'content': 'hi', 'imdisplayname': 'A', 'from': '8:orgid:A'},
    ])
    assert cli._main(['messages', '--chat', '19:x@unq.gbl.spaces']) == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]['chatId'] == '19:x@unq.gbl.spaces'


def test_main_messages_requires_exactly_one_target(stub_chatsvc):
    with pytest.raises(cli.UsageError, match='exactly one'):
        cli._main(['messages'])
    with pytest.raises(cli.UsageError, match='exactly one'):
        cli._main(['messages', '--channel', 'a', '--chat', 'b'])


def test_main_returns_1_when_api_returns_none(monkeypatch, stub_graph, capsys):
    monkeypatch.setattr(cli.api_mod, 'graph_get', lambda base, ep, tok, **k: None)
    assert cli._main(['teams']) == 1
    capsys.readouterr()


# --- global flags + surface ---------------------------------------------------

def test_main_debug_and_profile_flags(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.auth_mod, 'graph_setup',
                        lambda config, debug=False: seen.update(config=dict(config), debug=debug)
                        or ('tok', 'https://g'))
    monkeypatch.setattr(cli.api_mod, 'graph_get', lambda base, ep, tok, **k: {'value': []})
    assert cli._main(['--debug', '--profile', 'work', 'teams']) == 0
    assert seen['debug'] is True
    assert seen['config']['owa_piggy_profile'] == 'work'
    capsys.readouterr()


def test_main_profile_requires_value():
    with pytest.raises(cli.UsageError, match='--profile requires a value'):
        cli._main(['--profile'])


def test_main_unknown_command_is_usage_error(monkeypatch):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    with pytest.raises(cli.UsageError, match='Unknown command'):
        cli._main(['frobnicate'])


def test_main_unknown_flag_is_usage_error(monkeypatch, stub_graph):
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli._main(['teams', '--bogus'])


def test_config_via_main_keeps_profile_as_subflag(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.config_mod, 'config_set', lambda k, v: saved.__setitem__(k, v))
    assert cli._main(['config', '--profile', 'work']) == 0
    assert saved == {'owa_piggy_profile': 'work'}
    capsys.readouterr()


def test_config_sets_region_and_page_size(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.config_mod, 'config_set', lambda k, v: saved.__setitem__(k, v))
    assert cli._main(['config', '--region', 'AMER', '--page-size', '20']) == 0
    assert saved == {'teams_region': 'amer', 'page_size': '20'}
    capsys.readouterr()


def test_config_shows_current(monkeypatch, capsys):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {'teams_region': 'apac'})
    assert cli._main(['config']) == 0
    assert 'apac' in capsys.readouterr().err


def test_refresh_verifies_graph(monkeypatch, capsys):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.auth_mod, 'graph_setup', lambda config, debug=False: ('tok', 'https://g'))
    monkeypatch.setattr(cli.api_mod, 'graph_get',
                        lambda base, ep, tok, **k: {'displayName': 'Kim', 'userPrincipalName': 'k@x'})
    assert cli._main(['refresh']) == 0
    assert 'k@x' in capsys.readouterr().err


def test_teams_pretty_output(monkeypatch, capsys, stub_graph):
    monkeypatch.setattr(cli.api_mod, 'graph_get',
                        lambda base, ep, tok, **k: {'value': [{'id': 't1', 'displayName': 'Eng'}]})
    assert cli._main(['teams', '--pretty']) == 0
    out = capsys.readouterr().out
    assert 'Eng' in out and '{' not in out  # human table, not JSON


def test_channels_pretty_via_team_flag(monkeypatch, capsys, stub_graph):
    monkeypatch.setattr(cli.api_mod, 'graph_collect',
                        lambda base, ep, tok, **k: ([{'id': 'c1', 'displayName': 'Gen', 'membershipType': 'standard'}], False))
    assert cli._main(['channels', '--team', 'T1', '--pretty']) == 0
    assert 'standard' in capsys.readouterr().out


def test_messages_system_events_includes_system(monkeypatch, capsys, stub_chatsvc):
    monkeypatch.setattr(cli.api_mod, 'chatsvc_messages', lambda base, cid, tok, **k: [
        {'id': 's', 'messagetype': 'ThreadActivity/AddMember', 'content': '', 'properties': {}},
    ])
    assert cli._main(['messages', '--channel', 'c', '--system-events']) == 0
    out = json.loads(capsys.readouterr().out)
    assert out and out[0]['messageType'] == 'ThreadActivity/AddMember'


def test_messages_all_flag_is_rejected(stub_chatsvc):
    """--all was renamed to --system-events; the old flag must raise UsageError."""
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli._main(['messages', '--channel', 'c', '--all'])


def test_messages_truncation_note_on_stderr(monkeypatch, capsys, stub_chatsvc):
    """When raw messages == page_size * limit, a truncation note goes to stderr."""
    # default page_size is 50, default limit is 4 → 200 messages triggers the note
    page_size = 50
    limit = 4
    raw = [{'id': str(i), 'messagetype': 'Text', 'content': 'x',
            'imdisplayname': 'A', 'from': '8:orgid:A', 'properties': {}}
           for i in range(page_size * limit)]
    monkeypatch.setattr(cli.api_mod, 'chatsvc_messages', lambda base, cid, tok, **k: raw)
    assert cli._main(['messages', '--chat', '19:x@unq.gbl.spaces']) == 0
    captured = capsys.readouterr()
    assert 'truncated' in captured.err


def test_messages_no_truncation_note_below_cap(monkeypatch, capsys, stub_chatsvc):
    """When raw messages < page_size * limit, no truncation note is emitted."""
    raw = [{'id': '1', 'messagetype': 'Text', 'content': 'hi',
            'imdisplayname': 'A', 'from': '8:orgid:A', 'properties': {}}]
    monkeypatch.setattr(cli.api_mod, 'chatsvc_messages', lambda base, cid, tok, **k: raw)
    assert cli._main(['messages', '--chat', '19:x@unq.gbl.spaces']) == 0
    captured = capsys.readouterr()
    assert 'truncated' not in captured.err


def test_refresh_auth_failure_returns_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})

    def boom(config, debug=False):
        raise cli.OwaError('broker down')

    monkeypatch.setattr(cli.auth_mod, 'graph_setup', boom)
    rc = cli._main(['refresh'])
    assert rc != 0
    assert 'broker down' in capsys.readouterr().err


def test_refresh_verification_failure_returns_1(monkeypatch, capsys):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.auth_mod, 'graph_setup', lambda config, debug=False: ('tok', 'https://g'))
    monkeypatch.setattr(cli.api_mod, 'graph_get', lambda base, ep, tok, **k: None)
    assert cli._main(['refresh']) == 1
    assert 'verification failed' in capsys.readouterr().err.lower()


def test_main_no_args_prints_help(capsys):
    assert cli._main([]) == 0
    assert 'owa-teams' in capsys.readouterr().out


def test_main_function_wraps_dispatch(capsys):
    assert cli.main(['schema']) == 0
    assert json.loads(capsys.readouterr().out)['tool'] == 'owa-teams'


# --- paging (--top / --all) ---------------------------------------------------

def test_chats_top_forwarded_and_truncation_note(monkeypatch, capsys, stub_graph):
    seen = {}
    monkeypatch.setattr(cli.api_mod, 'graph_collect',
                        lambda base, ep, tok, **k: seen.update(k=k, ep=ep) or ([{'id': 'a'}], True))
    assert cli._main(['chats', '--top', '5']) == 0
    assert seen['k']['top'] == 5
    assert '$top=5' in seen['ep']  # page size is clamped to the requested top
    assert 'truncated' in capsys.readouterr().err


def test_chats_all_sends_top_none(monkeypatch, capsys, stub_graph):
    seen = {}
    monkeypatch.setattr(cli.api_mod, 'graph_collect',
                        lambda base, ep, tok, **k: seen.update(k=k) or ([{'id': 'a'}], False))
    assert cli._main(['chats', '--all']) == 0
    assert seen['k']['top'] is None
    assert 'truncated' not in capsys.readouterr().err


def test_channels_top_rejects_non_positive(stub_graph):
    with pytest.raises(cli.UsageError, match='positive integer'):
        cli._main(['channels', '--team', 'T', '--top', '0'])


def test_channels_truncation_note_and_pretty(monkeypatch, capsys, stub_graph):
    monkeypatch.setattr(cli.api_mod, 'graph_collect',
                        lambda base, ep, tok, **k: ([{'id': 'c1', 'displayName': 'Gen',
                                                      'membershipType': 'standard'}], True))
    assert cli._main(['channels', '--team', 'T', '--top', '1', '--pretty']) == 0
    captured = capsys.readouterr()
    assert 'standard' in captured.out
    assert 'truncated' in captured.err


# --- members ------------------------------------------------------------------

def test_members_chat_via_graph(monkeypatch, capsys, stub_graph):
    seen = {}
    monkeypatch.setattr(cli.api_mod, 'graph_paginate',
                        lambda base, ep, tok, **k: seen.update(ep=ep) or [
                            {'id': 'm1', 'displayName': 'Ada', 'email': 'a@x', 'roles': ['owner']}])
    assert cli._main(['members', '--chat', '19:c@thread.v2']) == 0
    assert 'chats/19%3Ac%40thread.v2/members' in seen['ep']
    assert json.loads(capsys.readouterr().out)[0]['displayName'] == 'Ada'


def test_members_channel_requires_team(stub_graph):
    with pytest.raises(cli.UsageError, match='requires --team'):
        cli._main(['members', '--channel', '19:c@thread.tacv2'])


def test_members_requires_exactly_one_target(stub_graph):
    with pytest.raises(cli.UsageError, match='exactly one'):
        cli._main(['members'])
    with pytest.raises(cli.UsageError, match='exactly one'):
        cli._main(['members', '--chat', 'a', '--channel', 'b', '--team', 't'])


def test_members_channel_uses_walled_endpoint(monkeypatch, capsys, stub_graph):
    seen = {}
    monkeypatch.setattr(cli.api_mod, 'graph_paginate',
                        lambda base, ep, tok, **k: seen.update(ep=ep) or [])
    assert cli._main(['members', '--channel', '19:c@thread.tacv2', '--team', 'T1']) == 0
    assert 'teams/T1/channels/' in seen['ep'] and seen['ep'].endswith('/members')
    capsys.readouterr()


def test_members_returns_1_when_api_returns_none(monkeypatch, capsys, stub_graph):
    monkeypatch.setattr(cli.api_mod, 'graph_paginate', lambda base, ep, tok, **k: None)
    assert cli._main(['members', '--chat', 'c']) == 1
    capsys.readouterr()


def test_members_pretty(monkeypatch, capsys, stub_graph):
    monkeypatch.setattr(cli.api_mod, 'graph_paginate',
                        lambda base, ep, tok, **k: [{'displayName': 'Ada', 'roles': ['owner'], 'email': 'a@x'}])
    assert cli._main(['members', '--chat', 'c', '--pretty']) == 0
    out = capsys.readouterr().out
    assert 'Ada' in out and 'owner' in out


# --- send ---------------------------------------------------------------------

def test_send_chat_posts_and_returns_result(monkeypatch, capsys, stub_chatsvc):
    seen = {}
    monkeypatch.setattr(cli.api_mod, 'chatsvc_post',
                        lambda base, cid, body, tok, **k: seen.update(cid=cid, body=body)
                        or {'OriginalArrivalTime': 123})
    assert cli._main(['send', '--chat', '19:x@unq.gbl.spaces', '--text', 'hi', '--confirm']) == 0
    out = json.loads(capsys.readouterr().out)
    assert seen['cid'] == '19:x@unq.gbl.spaces'
    assert out['sent'] is True
    assert out['originalArrivalTime'] == 123
    assert out['clientMessageId'] == seen['body']['clientmessageid']


def test_send_channel_subject_sets_thread_title(monkeypatch, capsys, stub_chatsvc):
    seen = {}
    monkeypatch.setattr(cli.api_mod, 'chatsvc_post',
                        lambda base, cid, body, tok, **k: seen.update(body=body) or {})
    assert cli._main(['send', '--channel', '19:c@thread.tacv2', '--subject', 'Q3',
                      '--text', 'kickoff', '--confirm']) == 0
    assert seen['body']['properties']['subject'] == 'Q3'
    capsys.readouterr()


def test_send_requires_exactly_one_target(stub_chatsvc):
    with pytest.raises(cli.UsageError, match='exactly one'):
        cli._main(['send', '--text', 'hi', '--confirm'])
    with pytest.raises(cli.UsageError, match='exactly one'):
        cli._main(['send', '--chat', 'a', '--channel', 'b', '--text', 'hi', '--confirm'])


def test_send_requires_body(stub_chatsvc):
    with pytest.raises(cli.UsageError, match='message body'):
        cli._main(['send', '--chat', 'a', '--confirm'])


def test_send_refuses_non_interactive_without_confirm(monkeypatch, stub_chatsvc):
    monkeypatch.setattr(cli.tty_mod, 'is_interactive', lambda **k: False)
    with pytest.raises(cli.UsageError, match='--confirm'):
        cli._main(['send', '--chat', 'a', '--text', 'hi'])


def test_send_channel_reply_threads_mentions_attachments(monkeypatch, capsys, stub_chatsvc):
    seen = {}
    monkeypatch.setattr(cli.api_mod, 'chatsvc_post',
                        lambda base, cid, body, tok, **k: seen.update(body=body)
                        or {'OriginalArrivalTime': 1})
    rc = cli._main([
        'send', '--channel', '19:c@thread.tacv2', '--reply-to', '999',
        '--text', 'agreed', '--mention', '8:orgid:oid=Ada',
        '--attachment', 'doc=https://x/f', '--confirm',
    ])
    assert rc == 0
    body = seen['body']
    props = body['properties']
    assert props['rootMessageId'] == '999'
    assert '<at id="0">Ada</at>' in body['content']
    assert '8:orgid:oid' in props['mentions']
    assert 'https://x/f' in props['files']
    capsys.readouterr()


def test_send_html_body_not_escaped(monkeypatch, capsys, stub_chatsvc):
    seen = {}
    monkeypatch.setattr(cli.api_mod, 'chatsvc_post',
                        lambda base, cid, body, tok, **k: seen.update(body=body) or {})
    assert cli._main(['send', '--chat', 'c', '--html', '--text', '<b>x</b>', '--confirm']) == 0
    assert seen['body']['content'] == '<b>x</b>'
    capsys.readouterr()


def test_send_region_override_forwarded(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.auth_mod, 'chatsvc_setup',
                        lambda config, debug=False, region=None:
                        seen.update(region=region) or ('tok', 'https://t/api/chatsvc/amer/v1'))
    monkeypatch.setattr(cli.api_mod, 'chatsvc_post', lambda base, cid, body, tok, **k: {})
    assert cli._main(['send', '--chat', 'c', '--text', 'hi', '--region', 'amer', '--confirm']) == 0
    assert seen['region'] == 'amer'
    capsys.readouterr()


def test_send_returns_1_when_post_returns_none(monkeypatch, capsys, stub_chatsvc):
    monkeypatch.setattr(cli.api_mod, 'chatsvc_post', lambda base, cid, body, tok, **k: None)
    assert cli._main(['send', '--chat', 'c', '--text', 'hi', '--confirm']) == 1
    capsys.readouterr()


def test_send_bad_mention_is_usage_error(stub_chatsvc):
    with pytest.raises(cli.UsageError, match='MRI'):
        cli._main(['send', '--chat', 'c', '--text', 'hi', '--mention', '=NoMri', '--confirm'])


def test_send_bad_attachment_is_usage_error(stub_chatsvc):
    with pytest.raises(cli.UsageError, match='url'):
        cli._main(['send', '--chat', 'c', '--text', 'hi', '--attachment', 'name=', '--confirm'])
