"""Pretty-printer shape detection and table formatting."""
from owa_graph import format as format_mod


def test_format_pretty_users_table():
    payload = {'value': [
        {'displayName': 'Alice', 'userPrincipalName': 'a@x.com', 'id': 'AAA'},
        {'displayName': 'Bob', 'userPrincipalName': 'b@x.com', 'id': 'BBB'},
    ]}
    out = format_mod.format_pretty(payload)
    assert 'Alice' in out
    assert 'a@x.com' in out
    assert 'AAA' in out
    # Two-line table - one row per user, no JSON braces.
    assert '\n' in out
    assert '{' not in out


def test_format_pretty_users_falls_back_to_mail_when_no_upn():
    payload = {'value': [
        {'displayName': 'Group A', 'mail': 'group@x.com', 'id': 'G1'},
    ]}
    out = format_mod.format_pretty(payload)
    assert 'group@x.com' in out


def test_format_pretty_messages_table():
    payload = {'value': [
        {
            'subject': 'Hello',
            'from': {'emailAddress': {'address': 'sender@x.com'}},
            'receivedDateTime': '2026-04-30T10:30:00Z',
        },
    ]}
    out = format_mod.format_pretty(payload)
    assert 'Hello' in out
    assert 'sender@x.com' in out
    # Date trimmed to YYYY-MM-DD HH:MM, T replaced with space.
    assert '2026-04-30 10:30' in out


def test_format_pretty_messages_uses_sender_when_from_missing():
    payload = {'value': [
        {
            'subject': 'Hi',
            'sender': {'emailAddress': {'address': 'svc@x.com'}},
            'receivedDateTime': '',
        },
    ]}
    assert 'svc@x.com' in format_mod.format_pretty(payload)


def test_format_pretty_drive_items_table():
    payload = {'value': [
        {'name': 'docs', 'folder': {'childCount': 3}, 'size': 0},
        {'name': 'report.pdf', 'file': {'mimeType': 'application/pdf'}, 'size': 12345},
    ]}
    out = format_mod.format_pretty(payload)
    # Folder marker 'd', file marker 'f'.
    assert 'docs' in out
    assert 'report.pdf' in out
    assert out.startswith('d') or '\nd' in out
    assert '\nf' in out
    assert '12345' in out


def test_format_pretty_unknown_collection_falls_back_to_indented_json():
    payload = {'value': [{'foo': 1}, {'foo': 2}]}
    out = format_mod.format_pretty(payload)
    # Unknown shape - indented JSON, two-space indent.
    assert '"foo"' in out
    assert '\n  ' in out


def test_format_pretty_non_collection_dict_indents_json():
    out = format_mod.format_pretty({'displayName': 'kim', 'id': 'x'})
    assert '"displayName"' in out
    assert '\n  ' in out


def test_format_pretty_empty_value_array_indents():
    payload = {'value': []}
    out = format_mod.format_pretty(payload)
    # Empty value - falls through to indented JSON, not a shape.
    assert '"value"' in out


def test_format_pretty_list_indents_as_json():
    out = format_mod.format_pretty([1, 2, 3])
    assert out.startswith('[')


def test_format_pretty_scalar_passes_through():
    assert format_mod.format_pretty('hello') == 'hello'
