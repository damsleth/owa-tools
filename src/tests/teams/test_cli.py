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
    monkeypatch.setattr(cli.api_mod, 'graph_paginate',
                        lambda base, ep, tok, **k: seen.update(ep=ep) or [{'id': 'c1', 'displayName': 'Gen'}])
    assert cli._main(['channels', 'TEAM-1']) == 0
    assert 'teams/TEAM-1/channels' in seen['ep']
    assert json.loads(capsys.readouterr().out)[0]['id'] == 'c1'


def test_main_channels_requires_team(stub_graph):
    with pytest.raises(cli.UsageError, match='requires --team'):
        cli._main(['channels'])


def test_main_routes_chats_with_type_filter(monkeypatch, capsys, stub_graph):
    monkeypatch.setattr(cli.api_mod, 'graph_paginate', lambda base, ep, tok, **k: [
        {'id': 'a', 'chatType': 'oneOnOne'}, {'id': 'b', 'chatType': 'meeting'},
    ])
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
    monkeypatch.setattr(cli.api_mod, 'graph_paginate',
                        lambda base, ep, tok, **k: [{'id': 'c1', 'displayName': 'Gen', 'membershipType': 'standard'}])
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
