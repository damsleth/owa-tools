"""Pretty-shape detectors + formatters for groups / teams / channels.

Each shape needs a discriminator that doesn't collide with the existing
users/messages/drive-items detectors and doesn't get pre-empted by them.
Fixture-shaped items are minimal: just enough fields for the detector
plus the columns the formatter prints.
"""
from owa_graph import format as fmt

# --- detector specificity --------------------------------------------------

def test_groups_detected_by_mail_enabled():
    items = [{'displayName': 'A', 'mail': 'a@x', 'mailEnabled': True, 'id': '1'}]
    assert fmt._looks_like_groups(items)
    assert not fmt._looks_like_teams(items)


def test_teams_detected_by_description_no_mail_enabled():
    items = [{'displayName': 'T', 'description': 'desc', 'id': '1'}]
    assert fmt._looks_like_teams(items)
    assert not fmt._looks_like_groups(items)


def test_channels_detected_by_teams_url():
    items = [{
        'displayName': 'General',
        'membershipType': 'standard',
        'webUrl': 'https://teams.microsoft.com/l/channel/...',
        'id': 'c1',
    }]
    assert fmt._looks_like_channels(items)


def test_channels_not_matched_when_url_missing():
    items = [{'displayName': 'General', 'id': 'c1'}]
    assert not fmt._looks_like_channels(items)


def test_teams_not_matched_when_mail_enabled_present():
    # A group also has displayName + sometimes description; the no-
    # mailEnabled clause is what separates teams from groups.
    items = [{'displayName': 'G', 'description': 'd', 'mailEnabled': True}]
    assert not fmt._looks_like_teams(items)


def test_users_still_matches_when_userprincipalname_present():
    items = [{'displayName': 'Kim', 'userPrincipalName': 'kim@x', 'id': '1'}]
    # Sanity: pre-existing users detector still fires; new shapes don't
    # accidentally claim user payloads.
    assert fmt._looks_like_users(items)
    assert not fmt._looks_like_groups(items)
    assert not fmt._looks_like_teams(items)


# --- formatter routing through format_pretty ------------------------------

def test_format_pretty_groups_table():
    payload = {'value': [
        {'displayName': 'A-team', 'mail': 'a@x', 'mailEnabled': True, 'id': 'id1'},
        {'displayName': 'B-team', 'mail': 'b@x', 'mailEnabled': True, 'id': 'id2'},
    ]}
    out = fmt.format_pretty(payload)
    assert 'A-team' in out
    assert 'a@x' in out
    assert 'id1' in out
    assert '\n' in out


def test_format_pretty_teams_table():
    payload = {'value': [
        {'displayName': 'Eng', 'description': 'engineering', 'id': 'tid1'},
        {'displayName': 'Ops', 'description': 'operations', 'id': 'tid2'},
    ]}
    out = fmt.format_pretty(payload)
    assert 'Eng' in out
    assert 'tid1' in out
    # Teams formatter is just name / id, mail column is groups-only.
    assert 'engineering' not in out


def test_format_pretty_channels_table():
    payload = {'value': [
        {'displayName': 'General',
         'membershipType': 'standard',
         'webUrl': 'https://teams.microsoft.com/l/channel/...',
         'id': 'cid1'},
    ]}
    out = fmt.format_pretty(payload)
    assert 'General' in out
    assert 'standard' in out
    assert 'cid1' in out


def test_groups_take_precedence_over_users():
    # A group payload also satisfies _looks_like_users (displayName).
    # The dispatch order must check groups first or users would steal it.
    payload = {'value': [
        {'displayName': 'G', 'mail': 'g@x', 'mailEnabled': True, 'id': 'i'},
    ]}
    out = fmt.format_pretty(payload)
    # Groups formatter emits the mail column; users formatter would emit
    # userPrincipalName. The presence of `g@x` in the absence of a UPN
    # field on the input proves we routed to the groups table.
    assert 'g@x' in out
