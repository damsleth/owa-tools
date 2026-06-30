"""Pure-function tests for owa_teams.teams (builders, normalizers, threading)."""

import datetime as dt

from owa_teams import teams

# --- ISO timestamp parsing ----------------------------------------------------

def test_parse_iso_handles_z_suffix():
    assert teams.parse_iso('2026-06-01T12:00:00Z') == dt.datetime(2026, 6, 1, 12, tzinfo=dt.timezone.utc)


def test_parse_iso_trims_overlong_fractional_seconds():
    # chatsvc emits 7-digit fractions, which fromisoformat rejects.
    parsed = teams.parse_iso('2026-06-02T08:17:12.4940000Z')
    assert parsed == dt.datetime(2026, 6, 2, 8, 17, 12, 494000, tzinfo=dt.timezone.utc)


def test_parse_iso_bare_date_is_midnight_utc():
    assert teams.parse_iso('2026-06-01') == dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)


def test_parse_iso_assumes_utc_for_naive():
    assert teams.parse_iso('2026-06-01T00:00:00') == dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)


def test_parse_iso_rejects_garbage_and_empty():
    assert teams.parse_iso('not-a-date') is None
    assert teams.parse_iso('') is None
    assert teams.parse_iso(None) is None
    assert teams.parse_iso('   ') is None


def test_message_datetime_reads_arrival_then_compose():
    assert teams.message_datetime({'originalarrivaltime': '2026-06-01T00:00:00Z'}) == \
        dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    assert teams.message_datetime({'composetime': '2026-06-02T00:00:00Z'}) == \
        dt.datetime(2026, 6, 2, tzinfo=dt.timezone.utc)
    assert teams.message_datetime({}) is None


# --- HTML stripping -----------------------------------------------------------

def test_strip_html_unwraps_mentions_and_tags():
    html = '<div>Hi <at id="0">Kim</at>, see <b>this</b></div>'
    assert teams.strip_html(html) == 'Hi Kim, see this'


def test_strip_html_drops_attachments_and_entities():
    assert teams.strip_html('<attachment id="x"></attachment><p>a&amp;b</p>') == 'a&b'


def test_strip_html_empty():
    assert teams.strip_html('') == ''
    assert teams.strip_html(None) == ''


# --- Graph endpoint builders --------------------------------------------------

def test_joined_teams_endpoint_has_no_query():
    # Graph 400s on $select/$top for /me/joinedTeams under delegated auth.
    assert teams.joined_teams_endpoint() == 'me/joinedTeams'


def test_channels_endpoint_selects_and_encodes():
    ep = teams.channels_endpoint('team/with space')
    assert ep.startswith('teams/team%2Fwith%20space/channels?$select=')
    assert 'membershipType' in ep


def test_chats_endpoint_top():
    ep = teams.chats_endpoint(top=25)
    assert ep.startswith('me/chats?$select=')
    assert '$top=25' in ep


def test_conversation_messages_url_encodes_id_and_view():
    url = teams.conversation_messages_url(
        'https://teams.microsoft.com/api/chatsvc/emea/v1',
        '19:abc@thread.tacv2', page_size=30,
    )
    assert '/users/ME/conversations/19%3Aabc%40thread.tacv2/messages' in url
    assert 'pageSize=30' in url
    assert 'view=msnp24Equivalent%7CsupportsMessageProperties' in url


# --- Graph normalizers --------------------------------------------------------

def test_normalize_teams():
    payload = {'value': [
        {'id': 't1', 'displayName': 'A', 'description': 'd', 'isArchived': False},
        {'displayName': 'no id'},  # dropped
    ]}
    rows = teams.normalize_teams(payload)
    assert rows == [{'id': 't1', 'displayName': 'A', 'description': 'd', 'isArchived': False}]


def test_normalize_channels():
    rows = teams.normalize_channels([
        {'id': 'c1', 'displayName': 'General', 'membershipType': 'standard'},
    ])
    assert rows[0]['membershipType'] == 'standard'
    assert rows[0]['isArchived'] is False


def test_normalize_chats_filters_by_type():
    payload = {'value': [
        {'id': 'a', 'chatType': 'oneOnOne', 'topic': None},
        {'id': 'b', 'chatType': 'meeting', 'topic': 'Standup'},
    ]}
    assert [c['id'] for c in teams.normalize_chats(payload)] == ['a', 'b']
    meeting = teams.normalize_chats(payload, chat_type='meeting')
    assert [c['id'] for c in meeting] == ['b']


# --- chatsvc message helpers --------------------------------------------------

def test_sender_extracts_oid_from_mri():
    s = teams._sender({'from': 'https://x/contacts/8:orgid:OID-1', 'imdisplayname': 'Kim'})
    assert s == {'id': 'OID-1', 'name': 'Kim', 'mri': '8:orgid:OID-1'}


def test_sender_falls_back_to_raw_mri():
    s = teams._sender({'from': '28:botid', 'imdisplayname': ''})
    assert s['mri'] == '28:botid'
    assert s['id'] == '28:botid'


def test_is_system_message():
    assert teams.is_system_message({'messagetype': 'ThreadActivity/AddMember'}) is True
    assert teams.is_system_message({'messagetype': 'RichText/Html'}) is False
    assert teams.is_system_message({'messagetype': 'Text'}) is False


def test_root_id_root_vs_reply():
    assert teams._root_id({'id': '5', 'rootMessageId': '5'}) == ('5', False)
    assert teams._root_id({'id': '5'}) == ('5', False)
    assert teams._root_id({'id': '6', 'rootMessageId': '0'}) == ('6', False)
    assert teams._root_id({'id': '6', 'rootMessageId': '5'}) == ('5', True)


def _channel_raw():
    """Newest-first, rootMessageId threading, parentmessageid null - the real shape."""
    return [
        {'id': '15', 'rootMessageId': '15', 'sequenceId': 15, 'messagetype': 'RichText/Html',
         'from': 'https://x/contacts/8:orgid:D', 'imdisplayname': 'David',
         'content': '<p>New post</p>', 'originalarrivaltime': '2023-09-07T18:00:00.0000000Z',
         'properties': {'subject': 'New post', 'parentmessageid': None}},
        {'id': '11', 'rootMessageId': '8', 'sequenceId': 11, 'messagetype': 'RichText/Html',
         'from': 'https://x/contacts/8:orgid:L', 'imdisplayname': 'Line',
         'content': '<div>reply two</div>', 'originalarrivaltime': '2022-11-01T08:17:12.494Z',
         'properties': {}},
        {'id': '8', 'rootMessageId': '8', 'sequenceId': 8, 'messagetype': 'RichText/Html',
         'from': 'https://x/contacts/8:orgid:D', 'imdisplayname': 'David',
         'content': '<div>root</div>', 'originalarrivaltime': '2022-10-17T08:16:53.428Z',
         'properties': {'subject': 'TV-aksjonen'}},
        {'id': 'sys', 'rootMessageId': 'sys', 'sequenceId': 7, 'messagetype': 'ThreadActivity/AddMember',
         'content': '', 'properties': {}},
    ]


def test_normalize_channel_messages_threads_and_orders():
    rows = teams.normalize_channel_messages(_channel_raw(), team_id='T', channel_id='19:CH@thread.tacv2')
    # system event dropped, chronological (seq ascending)
    assert [r['sequenceId'] for r in rows] == [8, 11, 15]
    root, reply, post2 = rows
    # root + reply share a thread keyed on rootMessageId; reply inherits subject
    assert root['threadId'] == '19:CH@thread.tacv2:8'
    assert reply['threadId'] == '19:CH@thread.tacv2:8'
    assert reply['isReply'] is True
    assert reply['subject'] == 'TV-aksjonen'
    assert root['isReply'] is False
    # second root is its own thread
    assert post2['threadId'] == '19:CH@thread.tacv2:15'
    # body stripped, sender resolved, team/channel echoed
    assert reply['content'] == 'reply two'
    assert reply['from'] == {'id': 'L', 'name': 'Line', 'mri': '8:orgid:L'}
    assert root['teamId'] == 'T'
    assert root['channelId'] == '19:CH@thread.tacv2'


def test_normalize_channel_messages_include_system_keeps_events():
    rows = teams.normalize_channel_messages(_channel_raw(), channel_id='c', include_system=True)
    assert any(r['messageType'] == 'ThreadActivity/AddMember' for r in rows)


def test_normalize_channel_messages_thread_id_without_channel():
    rows = teams.normalize_channel_messages(
        [{'id': '8', 'rootMessageId': '8', 'messagetype': 'Text', 'content': 'hi'}],
    )
    assert rows[0]['threadId'] == '8'


def test_normalize_chat_messages_is_flat():
    raw = [
        {'id': '2', 'messagetype': 'Text', 'content': 'second', 'imdisplayname': 'A',
         'from': 'https://x/contacts/8:orgid:A', 'originalarrivaltime': '2024-01-02T00:00:00Z'},
        {'id': '1', 'messagetype': 'RichText/Html', 'content': '<p>first</p>', 'imdisplayname': 'B',
         'from': 'https://x/contacts/8:orgid:B', 'composetime': '2024-01-01T00:00:00Z'},
    ]
    rows = teams.normalize_chat_messages(raw, chat_id='19:chat@unq.gbl.spaces')
    assert [r['id'] for r in rows] == ['1', '2']  # reversed to chronological
    assert all(r['threadId'] == '19:chat@unq.gbl.spaces' for r in rows)
    assert rows[0]['content'] == 'first'
    assert 'rootMessageId' not in rows[0]


def test_normalize_chat_messages_drops_system_and_empty():
    raw = [
        {'id': 's', 'messagetype': 'ThreadActivity/AddMember', 'content': 'x'},
        {'id': 'e', 'messagetype': 'Text', 'content': '   '},
    ]
    assert teams.normalize_chat_messages(raw, chat_id='c') == []


# --- endpoint builders --------------------------------------------------------

def test_chat_members_endpoint_quotes_id():
    assert teams.chat_members_endpoint('19:c@thread.v2') == 'chats/19%3Ac%40thread.v2/members'


def test_channel_members_endpoint_quotes_ids():
    ep = teams.channel_members_endpoint('T1', '19:c@thread.tacv2')
    assert ep == 'teams/T1/channels/19%3Ac%40thread.tacv2/members'


def test_conversation_post_url_drops_query():
    url = teams.conversation_post_url('https://t/api/chatsvc/emea/v1', '19:x@unq.gbl.spaces')
    assert url == 'https://t/api/chatsvc/emea/v1/users/ME/conversations/19%3Ax%40unq.gbl.spaces/messages'
    assert '?' not in url


# --- message body builders ----------------------------------------------------

def test_build_message_body_escapes_plain_text():
    body = teams.build_message_body('a < b & c')
    assert body['content'] == 'a &lt; b &amp; c'
    assert body['messagetype'] == 'RichText/Html'
    assert body['clientmessageid']  # idempotency key present


def test_build_message_body_html_passthrough():
    body = teams.build_message_body('<b>hi</b>', html=True)
    assert body['content'] == '<b>hi</b>'


def test_build_message_body_prepends_mention_tags_and_serializes():
    m = teams.build_mention(0, '8:orgid:oid', 'Ada')
    body = teams.build_message_body('hello', mentions=[m])
    assert '<at id="0">Ada</at>' in body['content']
    assert body['content'].endswith('hello')
    import json as _json
    assert _json.loads(body['properties']['mentions'])[0]['mri'] == '8:orgid:oid'


def test_build_message_body_attachments_and_thread_props():
    f = teams.build_file_attachment(0, 'doc', 'https://x/f')
    body = teams.build_message_body('hi', attachments=[f], root_message_id='99', subject='Topic')
    import json as _json
    files = _json.loads(body['properties']['files'])
    assert files[0]['objectUrl'] == 'https://x/f'
    assert body['properties']['rootMessageId'] == '99'
    assert body['properties']['subject'] == 'Topic'


def test_build_message_body_no_properties_when_plain():
    body = teams.build_message_body('hi')
    assert 'properties' not in body


def test_client_message_id_is_unique():
    a = teams.build_message_body('x')['clientmessageid']
    b = teams.build_message_body('x')['clientmessageid']
    assert a != b and a.isdigit()


# --- members + send normalizers -----------------------------------------------

def test_normalize_members_maps_fields():
    payload = {'value': [{'id': 'm1', 'displayName': 'Ada', 'email': 'a@x',
                          'userId': 'u1', 'roles': ['owner']}]}
    rows = teams.normalize_members(payload)
    assert rows == [{'id': 'm1', 'displayName': 'Ada', 'email': 'a@x',
                     'userId': 'u1', 'roles': ['owner']}]


def test_normalize_members_defaults_roles_to_empty_list():
    rows = teams.normalize_members({'value': [{'id': 'm1'}]})
    assert rows[0]['roles'] == []


def test_normalize_send_result_echoes_key_and_arrival():
    body = {'clientmessageid': '123'}
    row = teams.normalize_send_result('19:x', body, {'OriginalArrivalTime': 7})
    assert row == {'sent': True, 'conversationId': '19:x',
                   'clientMessageId': '123', 'originalArrivalTime': 7}


def test_normalize_send_result_tolerates_non_dict_payload():
    row = teams.normalize_send_result('c', {'clientmessageid': '1'}, None)
    assert row['originalArrivalTime'] is None
