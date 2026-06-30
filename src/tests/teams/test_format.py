"""Pretty-output tests for owa_teams.format."""

from owa_teams import format as fmt


def test_format_teams_pretty():
    assert fmt.format_teams_pretty([]) == 'No teams found.'
    out = fmt.format_teams_pretty([{'displayName': 'Eng', 'id': 't1', 'isArchived': False}])
    assert 'Eng' in out and 't1' in out
    archived = fmt.format_teams_pretty([{'displayName': 'Old', 'id': 't2', 'isArchived': True}])
    assert '(archived)' in archived


def test_format_channels_pretty():
    assert fmt.format_channels_pretty([]) == 'No channels found.'
    out = fmt.format_channels_pretty([{'displayName': 'General', 'membershipType': 'standard', 'id': 'c1'}])
    assert 'General' in out and 'standard' in out and 'c1' in out


def test_format_chats_pretty():
    assert fmt.format_chats_pretty([]) == 'No chats found.'
    out = fmt.format_chats_pretty([{'chatType': 'meeting', 'topic': 'Standup', 'id': 'x'}])
    assert 'meeting' in out and 'Standup' in out
    no_topic = fmt.format_chats_pretty([{'chatType': 'oneOnOne', 'topic': None, 'id': 'y'}])
    assert '(no topic)' in no_topic


def test_format_messages_pretty_threads_subjects_and_indents_replies():
    rows = [
        {'from': {'name': 'David'}, 'timestamp': '2022-10-17T08:16:53Z',
         'subject': 'TV-aksjonen', 'isReply': False, 'content': 'root'},
        {'from': {'name': 'Line'}, 'timestamp': '2022-11-01T08:17:12Z',
         'subject': 'TV-aksjonen', 'isReply': True, 'content': 'reply'},
    ]
    out = fmt.format_messages_pretty(rows)
    lines = out.splitlines()
    assert lines[0] == '# TV-aksjonen'  # subject header printed once
    assert lines.count('# TV-aksjonen') == 1
    assert any(line.startswith('    ') and 'Line' in line for line in lines)  # reply indented deeper


def test_format_messages_pretty_empty():
    assert fmt.format_messages_pretty([]) == 'No messages.'


def test_format_messages_pretty_falls_back_to_sender_id():
    out = fmt.format_messages_pretty([{'from': {'id': 'OID', 'name': ''}, 'timestamp': '', 'content': 'hi'}])
    assert 'OID' in out


def test_format_members_pretty_empty():
    assert fmt.format_members_pretty([]) == 'No members found.'


def test_format_members_pretty_row():
    out = fmt.format_members_pretty([{'displayName': 'Ada', 'roles': ['owner'], 'email': 'a@x'}])
    assert 'Ada' in out and 'owner' in out and 'a@x' in out


def test_format_members_pretty_defaults_role_to_member():
    out = fmt.format_members_pretty([{'displayName': 'Bo', 'roles': [], 'email': 'b@x'}])
    assert 'member' in out
