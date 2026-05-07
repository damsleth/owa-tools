"""Tests for --pretty rendering."""
from owa_mail.format import (
    format_folders_pretty,
    format_message_pretty,
    format_messages_pretty,
)


def test_format_messages_pretty_empty():
    assert format_messages_pretty([]) == 'No messages found.'


def test_format_messages_pretty_sorts_newest_first():
    messages = [
        {'received': '2026-04-29T08:00:00Z', 'subject': 'old', 'from': 'a@b.c', 'is_read': True},
        {'received': '2026-04-30T08:00:00Z', 'subject': 'new', 'from': 'd@e.f', 'is_read': True},
    ]
    out = format_messages_pretty(messages)
    lines = out.splitlines()
    assert 'new' in lines[0]
    assert 'old' in lines[1]


def test_format_messages_pretty_unread_marker():
    messages = [
        {'received': '2026-04-30T08:00:00Z', 'subject': 's', 'from': 'a@b.c', 'is_read': False}
    ]
    out = format_messages_pretty(messages)
    # Unread marker is '*'; read uses ' '.
    assert '*' in out


def test_format_messages_pretty_handles_attachments_and_flag():
    messages = [{
        'received': '2026-04-30T08:00:00Z',
        'subject': 's', 'from': 'a@b.c',
        'is_read': True,
        'has_attachments': True,
        'flag': 'Flagged',
    }]
    out = format_messages_pretty(messages)
    assert '@' in out
    assert '!' in out


def test_format_message_pretty_includes_headers():
    msg = {
        'from': 'a@b.c',
        'to': 'me@b.c',
        'subject': 's',
        'received': '2026-04-30T08:00:00Z',
        'body': 'hi',
        'body_type': 'Text',
    }
    out = format_message_pretty(msg)
    assert 'From: a@b.c' in out
    assert 'Subject: s' in out
    assert 'hi' in out


def test_format_message_pretty_omits_empty_headers():
    msg = {'from': '', 'to': 'me@b.c', 'subject': 's', 'body': '', 'body_type': ''}
    out = format_message_pretty(msg)
    assert 'From:' not in out
    assert 'To: me@b.c' in out


def test_format_folders_pretty_empty():
    assert format_folders_pretty([]) == 'No folders.'


def test_format_folders_pretty_aligns_names():
    folders = [
        {'name': 'Inbox', 'unread': 5, 'total': 42},
        {'name': 'SentItems', 'unread': 0, 'total': 100},
    ]
    out = format_folders_pretty(folders)
    assert 'Inbox' in out
    assert 'unread=5' in out
    assert 'total=100' in out
