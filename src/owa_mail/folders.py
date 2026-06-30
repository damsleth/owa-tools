"""Mail folder helpers.

Outlook REST accepts well-known folder names directly in URL segments
(`me/MailFolders/Inbox/messages`), so the common case needs no API
lookup. resolve_folder_id normalises user input to the canonical casing
the API expects, or passes opaque folder ids through untouched.
"""
from .messages import _pick_str

# Canonical names accepted by Outlook REST as path segments. The map
# value is the exact casing the API wants; keys are lowercase for
# case-insensitive matching of user input. Aliases ("sent",
# "trash", "archived") reduce friction without inventing new vocabulary.
WELL_KNOWN = {
    'inbox': 'Inbox',
    'drafts': 'Drafts',
    'draft': 'Drafts',
    'sentitems': 'SentItems',
    'sent': 'SentItems',
    'deleteditems': 'DeletedItems',
    'deleted': 'DeletedItems',
    'trash': 'DeletedItems',
    'junk': 'JunkEmail',
    'junkemail': 'JunkEmail',
    'spam': 'JunkEmail',
    'outbox': 'Outbox',
    'archive': 'Archive',
    'archived': 'Archive',
}


def resolve_folder_id(name_or_id):
    """Normalise a well-known name to canonical casing, or return the
    input as-is if it doesn't match (assumed to be an opaque folder id).

    Empty input defaults to Inbox - the natural starting point for a
    mail CLI.
    """
    if not name_or_id:
        return 'Inbox'
    return WELL_KNOWN.get(name_or_id.strip().lower(), name_or_id.strip())


def is_well_known(name_or_id):
    """True when the input maps to a canonical well-known folder name."""
    if not name_or_id:
        return True
    return name_or_id.strip().lower() in WELL_KNOWN


def folder_lookup_query(display_name):
    """OData params (dict) to find a folder by its DisplayName.

    Outlook REST DisplayName is case-sensitive in $filter eq; callers
    that want a case-insensitive match should compare client-side.
    """
    esc = display_name.replace("'", "''")
    return {'$select': 'Id,DisplayName', '$filter': f"DisplayName eq '{esc}'"}


def pick_folder_id(folders, display_name):
    """From a normalized folder list, return the id whose name matches
    `display_name` (case-insensitive), or '' when none match."""
    target = display_name.strip().lower()
    for f in folders:
        if (f.get('name') or '').strip().lower() == target:
            return f.get('id') or ''
    return ''


def folder_messages_path(folder):
    """Build the messages-collection path for a folder."""
    return f'me/MailFolders/{resolve_folder_id(folder)}/messages'


def normalize_folder(raw):
    """Flatten an Outlook MailFolder object to our snake_case shape."""
    if not isinstance(raw, dict):
        return {}
    return {
        'id': _pick_str(raw, 'Id', 'id'),
        'name': _pick_str(raw, 'DisplayName', 'displayName'),
        'unread': raw.get('UnreadItemCount', raw.get('unreadItemCount', 0)) or 0,
        'total': raw.get('TotalItemCount', raw.get('totalItemCount', 0)) or 0,
    }


def normalize_folders(raw):
    items = raw.get('value', []) if isinstance(raw, dict) else []
    return [normalize_folder(f) for f in items]
