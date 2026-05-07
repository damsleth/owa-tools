"""Tests for folder name resolution."""
from owa_mail.folders import (
    folder_messages_path,
    normalize_folder,
    normalize_folders,
    resolve_folder_id,
)


def test_resolve_well_known_canonical():
    assert resolve_folder_id('Inbox') == 'Inbox'
    assert resolve_folder_id('SentItems') == 'SentItems'


def test_resolve_well_known_case_insensitive():
    assert resolve_folder_id('inbox') == 'Inbox'
    assert resolve_folder_id('INBOX') == 'Inbox'
    assert resolve_folder_id('  Inbox  ') == 'Inbox'


def test_resolve_well_known_aliases():
    assert resolve_folder_id('sent') == 'SentItems'
    assert resolve_folder_id('trash') == 'DeletedItems'
    assert resolve_folder_id('deleted') == 'DeletedItems'
    assert resolve_folder_id('junk') == 'JunkEmail'
    assert resolve_folder_id('spam') == 'JunkEmail'
    assert resolve_folder_id('archive') == 'Archive'
    assert resolve_folder_id('archived') == 'Archive'
    assert resolve_folder_id('draft') == 'Drafts'


def test_resolve_empty_defaults_to_inbox():
    assert resolve_folder_id('') == 'Inbox'
    assert resolve_folder_id(None) == 'Inbox'


def test_resolve_passes_through_opaque_id():
    opaque = 'AAMkAGI2NGM5N2VlLTRkZGI'
    assert resolve_folder_id(opaque) == opaque


def test_folder_messages_path():
    assert folder_messages_path('inbox') == 'me/MailFolders/Inbox/messages'
    assert folder_messages_path('') == 'me/MailFolders/Inbox/messages'
    assert folder_messages_path('archive') == 'me/MailFolders/Archive/messages'


def test_normalize_folder_pascal_case():
    raw = {
        'Id': 'AAA',
        'DisplayName': 'Inbox',
        'UnreadItemCount': 5,
        'TotalItemCount': 42,
    }
    flat = normalize_folder(raw)
    assert flat == {'id': 'AAA', 'name': 'Inbox', 'unread': 5, 'total': 42}


def test_normalize_folder_camel_case():
    raw = {
        'id': 'BBB',
        'displayName': 'Custom',
        'unreadItemCount': 0,
        'totalItemCount': 10,
    }
    flat = normalize_folder(raw)
    assert flat['name'] == 'Custom'
    assert flat['unread'] == 0
    assert flat['total'] == 10


def test_normalize_folders_collection():
    raw = {'value': [{'Id': '1', 'DisplayName': 'A'}, {'Id': '2', 'DisplayName': 'B'}]}
    flat = normalize_folders(raw)
    assert [f['name'] for f in flat] == ['A', 'B']


def test_normalize_folders_handles_empty():
    assert normalize_folders({}) == []
    assert normalize_folders(None) == []
