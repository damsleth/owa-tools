"""Pretty shapes for applications and audit logs.

Applications must dispatch before users since both shapes carry
`displayName`. The discriminator is `appId` in canonical UUID form.
"""
from owa_graph import format as fmt


# --- detectors -------------------------------------------------------------

def test_uuid_shape_recognises_canonical():
    assert fmt._is_uuid_shape('3346dce8-f416-4fa6-93da-90e68882aea8')


def test_uuid_shape_rejects_wrong_lengths_and_layouts():
    assert not fmt._is_uuid_shape('not-a-uuid')
    assert not fmt._is_uuid_shape('3346dce8f4164fa693da90e68882aea8')   # no dashes
    assert not fmt._is_uuid_shape('3346dce8-f416-4fa6-93da-90e68882aea')  # 35 chars
    assert not fmt._is_uuid_shape(None)


def test_applications_detected_by_app_id_uuid():
    items = [{'displayName': 'App',
              'appId': '3346dce8-f416-4fa6-93da-90e68882aea8',
              'id': 'objid'}]
    assert fmt._looks_like_applications(items)


def test_applications_rejected_when_app_id_missing():
    items = [{'displayName': 'App', 'id': 'objid'}]
    assert not fmt._looks_like_applications(items)


def test_audit_logs_detected_by_activity_fields():
    items = [{
        'activityDateTime': '2026-05-04T10:00:00Z',
        'activityDisplayName': 'Sign-in',
    }]
    assert fmt._looks_like_audit_logs(items)


def test_audit_logs_not_matched_without_activity_display_name():
    items = [{'activityDateTime': '2026-05-04T10:00:00Z'}]
    assert not fmt._looks_like_audit_logs(items)


# --- formatters -----------------------------------------------------------

def test_format_pretty_applications_table():
    payload = {'value': [
        {'displayName': 'TestApp',
         'appId': '3346dce8-f416-4fa6-93da-90e68882aea8',
         'id': 'objid'},
    ]}
    out = fmt.format_pretty(payload)
    assert 'TestApp' in out
    assert '3346dce8-f416-4fa6-93da-90e68882aea8' in out


def test_format_pretty_audit_logs_user_actor():
    payload = {'value': [
        {'activityDateTime': '2026-05-04T10:11:12Z',
         'activityDisplayName': 'Add user',
         'initiatedBy': {'user': {'userPrincipalName': 'admin@x'}}},
    ]}
    out = fmt.format_pretty(payload)
    assert '2026-05-04 10:11:12' in out
    assert 'admin@x' in out
    assert 'Add user' in out


def test_format_pretty_audit_logs_app_actor_fallback():
    payload = {'value': [
        {'activityDateTime': '2026-05-04T10:11:12Z',
         'activityDisplayName': 'Update policy',
         'initiatedBy': {'app': {'displayName': 'Sync Service'}}},
    ]}
    out = fmt.format_pretty(payload)
    assert 'Sync Service' in out


def test_applications_not_misclaimed_as_teams():
    # Live tenants emit application records with `description: null`
    # alongside displayName. The teams detector previously accepted any
    # dict with the `description` key (regardless of value) and stole
    # the routing. Lock the fix.
    items = [{
        'displayName': 'TestApp',
        'description': None,
        'appId': '3346dce8-f416-4fa6-93da-90e68882aea8',
        'id': 'objid',
    }]
    from owa_graph import format as fmt2
    assert not fmt2._looks_like_teams(items)
    assert fmt2._looks_like_applications(items)


def test_applications_take_precedence_over_users():
    # Applications carry `displayName`, which would otherwise route to
    # the users table. Order in format_pretty must check applications
    # first; appId in UUID shape is what makes them distinguishable.
    payload = {'value': [
        {'displayName': 'TestApp',
         'appId': '3346dce8-f416-4fa6-93da-90e68882aea8',
         'id': 'objid'},
    ]}
    out = fmt.format_pretty(payload)
    # The applications formatter prints appId; the users formatter
    # would print id (a different value here) or UPN.
    assert '3346dce8-f416-4fa6-93da-90e68882aea8' in out
