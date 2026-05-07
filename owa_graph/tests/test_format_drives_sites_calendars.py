"""Pretty shapes for drives / sites / calendars.

Drive and site payloads both carry a sharepoint.com webUrl, so the
dispatcher checks `driveType` first to keep them separated.
"""
from owa_graph import format as fmt


# --- detectors -------------------------------------------------------------

def test_drives_detected_by_drive_type():
    items = [{'name': 'OneDrive', 'driveType': 'business', 'id': 'd1'}]
    assert fmt._looks_like_drives(items)
    assert not fmt._looks_like_sites(items)


def test_drives_rejects_unknown_type():
    items = [{'name': 'X', 'driveType': 'unknown'}]
    assert not fmt._looks_like_drives(items)


def test_sites_detected_by_sharepoint_url():
    items = [{
        'displayName': 'Marketing',
        'webUrl': 'https://contoso.sharepoint.com/sites/marketing',
        'id': 's1',
    }]
    assert fmt._looks_like_sites(items)


def test_sites_rejects_non_sharepoint_url():
    items = [{'displayName': 'X', 'webUrl': 'https://example.com'}]
    assert not fmt._looks_like_sites(items)


def test_calendars_detected_by_can_edit_bool():
    items = [{'name': 'Calendar', 'canEdit': True}]
    assert fmt._looks_like_calendars(items)


def test_calendars_rejects_truthy_non_bool():
    items = [{'name': 'Calendar', 'canEdit': 1}]
    # Calendars genuinely emit Booleans; an int 1 is suspicious enough
    # to skip the table.
    assert not fmt._looks_like_calendars(items)


# --- formatters -----------------------------------------------------------

def test_format_pretty_drives_table():
    payload = {'value': [
        {'name': 'OneDrive', 'driveType': 'business', 'id': 'd1'},
    ]}
    out = fmt.format_pretty(payload)
    assert 'OneDrive' in out
    assert 'business' in out
    assert 'd1' in out


def test_format_pretty_sites_table():
    payload = {'value': [
        {'displayName': 'Marketing',
         'webUrl': 'https://contoso.sharepoint.com/sites/marketing',
         'id': 's1'},
    ]}
    out = fmt.format_pretty(payload)
    assert 'Marketing' in out
    assert 'sharepoint.com' in out


def test_format_pretty_calendars_table():
    payload = {'value': [
        {'name': 'Calendar', 'canEdit': True,
         'owner': {'name': 'Kim', 'address': 'kim@x'}, 'id': 'c1'},
    ]}
    out = fmt.format_pretty(payload)
    assert 'Calendar' in out
    assert 'kim@x' in out
    assert 'c1' in out


def test_drives_take_precedence_over_sites():
    # A business drive lives on sharepoint.com, so the site detector
    # would also match. The dispatch order must check drives first.
    payload = {'value': [
        {'name': 'OneDrive',
         'displayName': 'OneDrive',  # not normally present, but worst-case
         'driveType': 'business',
         'webUrl': 'https://contoso.sharepoint.com/personal/foo',
         'id': 'd1'},
    ]}
    out = fmt.format_pretty(payload)
    # drives formatter prints driveType column; sites formatter doesn't.
    assert 'business' in out
