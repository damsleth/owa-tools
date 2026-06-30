"""Tests for message normalization and JSON-shape builders."""
import pytest

from owa_mail.messages import (
    LIST_SELECT,
    LIST_SELECT_WITH_BODY,
    build_draft_payload,
    build_list_query,
    build_mark_patch,
    build_message_body,
    build_reply_patch,
    build_send_payload,
    message_path,
    normalize_message,
    normalize_messages,
)


def test_normalize_message_flattens_pascal_case():
    raw = {
        'Id': 'AAMkAG',
        'ConversationId': 'CONV1',
        'ReceivedDateTime': '2026-04-30T10:00:00Z',
        'Subject': 'Hello',
        'From': {'EmailAddress': {'Address': 'a@example.com', 'Name': 'A'}},
        'ToRecipients': [
            {'EmailAddress': {'Address': 'b@example.com'}},
            {'EmailAddress': {'Address': 'c@example.com'}},
        ],
        'CcRecipients': [],
        'BodyPreview': 'Hi there',
        'IsRead': False,
        'HasAttachments': True,
        'Importance': 'High',
        'Flag': {'FlagStatus': 'Flagged'},
        'WebLink': 'https://outlook/...',
        'ParentFolderId': 'F1',
        'Body': {'ContentType': 'Text', 'Content': 'body text'},
    }
    flat = normalize_message(raw)
    assert flat['id'] == 'AAMkAG'
    assert flat['from'] == 'a@example.com'
    assert flat['to'] == 'b@example.com, c@example.com'
    assert flat['cc'] == ''
    assert flat['preview'] == 'Hi there'
    assert flat['is_read'] is False
    assert flat['has_attachments'] is True
    assert flat['flag'] == 'Flagged'
    assert flat['body_type'] == 'Text'
    assert flat['body'] == 'body text'


def test_normalize_messages_drops_body_from_list():
    raw = {
        'value': [
            {
                'Id': '1',
                'Subject': 'a',
                'Body': {'ContentType': 'Text', 'Content': 'hi'},
                'InternetMessageHeaders': [{'Name': 'X-Foo', 'Value': 'bar'}],
            }
        ]
    }
    flat = normalize_messages(raw)
    assert len(flat) == 1
    assert flat[0]['subject'] == 'a'
    # Body fields are stripped from listings to keep the payload tight.
    assert 'body' not in flat[0]
    assert 'body_type' not in flat[0]
    assert 'internet_headers' not in flat[0]


def test_normalize_messages_keep_body_preserves_body_and_headers():
    raw = {
        'value': [
            {
                'Id': '1',
                'Subject': 'a',
                'Body': {'ContentType': 'HTML', 'Content': '<p>hi</p>'},
                'InternetMessageHeaders': [
                    {'Name': 'List-Unsubscribe', 'Value': '<mailto:u@x>'},
                    {'Name': 'Auto-Submitted', 'Value': 'auto-generated'},
                ],
            }
        ]
    }
    flat = normalize_messages(raw, keep_body=True)
    assert flat[0]['body'] == '<p>hi</p>'
    assert flat[0]['body_type'] == 'HTML'
    assert flat[0]['internet_headers'] == [
        {'name': 'List-Unsubscribe', 'value': '<mailto:u@x>'},
        {'name': 'Auto-Submitted', 'value': 'auto-generated'},
    ]


def test_list_select_with_body_includes_body_and_headers():
    assert 'Body' in LIST_SELECT_WITH_BODY
    assert 'InternetMessageHeaders' in LIST_SELECT_WITH_BODY


def test_normalize_message_extracts_internet_headers():
    raw = {
        'Id': '1',
        'InternetMessageHeaders': [
            {'name': 'List-Id', 'value': 'foo'},  # camelCase variant
            {'Name': 'Precedence', 'Value': 'bulk'},
            'not-a-dict',
            {'value': 'no-name'},
        ],
    }
    flat = normalize_message(raw)
    assert flat['internet_headers'] == [
        {'name': 'List-Id', 'value': 'foo'},
        {'name': 'Precedence', 'value': 'bulk'},
    ]


def test_normalize_message_handles_camel_case():
    raw = {
        'id': '1',
        'subject': 'lower',
        'from': {'emailAddress': {'address': 'x@y'}},
    }
    flat = normalize_message(raw)
    assert flat['subject'] == 'lower'
    assert flat['from'] == 'x@y'


def test_normalize_message_handles_empty():
    assert normalize_message(None) == {}
    assert normalize_message({}) == {
        'id': '', 'conversation_id': '', 'received': '', 'sent': '',
        'subject': '', 'from': '', 'to': '', 'cc': '', 'bcc': '',
        'preview': '', 'is_read': False, 'has_attachments': False,
        'importance': '', 'flag': '', 'categories': [], 'folder_id': '',
        'web_link': '', 'body_type': '', 'body': '', 'internet_headers': [],
    }


# ---------- build_message_body ----------

def test_build_message_body_minimal():
    msg = build_message_body(
        to='a@example.com', cc='', bcc='',
        subject='hi', body='hello', html=False,
    )
    assert msg['Subject'] == 'hi'
    assert msg['Body'] == {'ContentType': 'Text', 'Content': 'hello'}
    assert msg['ToRecipients'] == [{'EmailAddress': {'Address': 'a@example.com'}}]
    assert 'CcRecipients' not in msg
    assert 'BccRecipients' not in msg


def test_build_message_body_html_switches_content_type():
    msg = build_message_body(
        to='a@example.com', cc='', bcc='',
        subject='hi', body='<p>hi</p>', html=True,
    )
    assert msg['Body']['ContentType'] == 'HTML'


def test_build_message_body_splits_recipients_on_comma_and_semicolon():
    msg = build_message_body(
        to='a@example.com, b@example.com; c@example.com',
        cc='', bcc='', subject='s', body='', html=False,
    )
    assert [r['EmailAddress']['Address'] for r in msg['ToRecipients']] == [
        'a@example.com', 'b@example.com', 'c@example.com',
    ]


def test_build_message_body_requires_to():
    with pytest.raises(ValueError):
        build_message_body(to='', cc='', bcc='', subject='s', body='', html=False)


def test_build_message_body_requires_subject():
    with pytest.raises(ValueError):
        build_message_body(to='a@b.c', cc='', bcc='', subject='', body='', html=False)


def test_build_message_body_importance_normalised():
    msg = build_message_body(
        to='a@b.c', cc='', bcc='', subject='s', body='', html=False, importance='HIGH',
    )
    assert msg['Importance'] == 'High'


def test_build_message_body_invalid_importance():
    with pytest.raises(ValueError):
        build_message_body(
            to='a@b.c', cc='', bcc='', subject='s', body='', html=False, importance='urgent',
        )


def test_build_send_payload_wraps_message():
    msg = {'Subject': 's'}
    payload = build_send_payload(msg)
    assert payload == {'Message': {'Subject': 's'}, 'SaveToSentItems': True}


def test_build_draft_payload_without_send_at():
    msg = {'Subject': 's'}
    payload = build_draft_payload(msg)
    assert payload == {'Subject': 's'}
    assert 'SingleValueExtendedProperties' not in payload


def test_build_draft_payload_with_send_at_attaches_extended_property():
    msg = {'Subject': 's'}
    payload = build_draft_payload(msg, send_at='2026-05-01T09:00:00Z')
    props = payload['SingleValueExtendedProperties']
    assert isinstance(props, list)
    assert len(props) == 1
    assert props[0]['PropertyId'] == 'SystemTime 0x3FEF'
    assert props[0]['Value'].endswith('Z')


def test_build_draft_payload_does_not_mutate_input():
    msg = {'Subject': 's'}
    build_draft_payload(msg, send_at='2026-05-01T09:00:00Z')
    assert 'SingleValueExtendedProperties' not in msg


# ---------- build_reply_patch ----------

def test_build_reply_patch_text():
    patch = build_reply_patch(body='thanks', html=False)
    assert patch['Body'] == {'ContentType': 'Text', 'Content': 'thanks'}
    assert 'ToRecipients' not in patch
    assert 'SingleValueExtendedProperties' not in patch


def test_build_reply_patch_omits_body_when_not_provided():
    assert build_reply_patch(body=None, html=False) == {}


def test_build_reply_patch_forward_with_extra_to():
    patch = build_reply_patch(body='fyi', html=False, extra_to='a@b.c, d@e.f')
    assert [r['EmailAddress']['Address'] for r in patch['ToRecipients']] == [
        'a@b.c', 'd@e.f',
    ]


def test_build_reply_patch_with_send_at():
    patch = build_reply_patch(body='later', html=False, send_at='2026-05-01T09:00:00Z')
    assert patch['SingleValueExtendedProperties'][0]['PropertyId'] == 'SystemTime 0x3FEF'


# ---------- build_mark_patch ----------

def test_build_mark_patch_read():
    assert build_mark_patch(read=True) == {'IsRead': True}
    assert build_mark_patch(read=False) == {'IsRead': False}


def test_build_mark_patch_flag():
    assert build_mark_patch(flag=True) == {'Flag': {'FlagStatus': 'Flagged'}}
    assert build_mark_patch(flag=False) == {'Flag': {'FlagStatus': 'NotFlagged'}}


def test_build_mark_patch_combined():
    patch = build_mark_patch(read=True, flag=True)
    assert patch == {'IsRead': True, 'Flag': {'FlagStatus': 'Flagged'}}


def test_build_mark_patch_neither():
    assert build_mark_patch() == {}


def test_message_path_url_encodes_id():
    assert message_path('AAMkAG=') == 'me/messages/AAMkAG%3D'
    assert message_path('a/b c') == 'me/messages/a%2Fb%20c'


def test_build_list_query_default_has_orderby():
    params = build_list_query()
    assert params['$top'] == 25
    assert params['$select'] == LIST_SELECT
    assert params['$orderby'] == 'ReceivedDateTime desc'
    assert '$filter' not in params
    assert '$search' not in params


def test_build_list_query_search_drops_orderby():
    # $search and $orderby are mutually exclusive in Outlook/Graph (HTTP 400).
    # The fix in build_list_query pops $orderby before setting $search.
    params = build_list_query(search='budget')
    assert params['$search'] == '"budget"'
    assert '$filter' not in params
    assert '$orderby' not in params


def test_build_list_query_sender_drops_orderby_and_escapes_quote():
    params = build_list_query(sender="O'Brien@example.com")
    assert '$orderby' not in params
    assert params['$filter'] == "contains(From/EmailAddress/Address,'O''Brien@example.com')"


def test_build_list_query_subject_drops_orderby():
    params = build_list_query(subject_q='quarterly')
    assert '$orderby' not in params
    assert params['$filter'] == "contains(Subject,'quarterly')"


def test_build_list_query_unread_keeps_orderby():
    params = build_list_query(unread=True)
    assert params['$orderby'] == 'ReceivedDateTime desc'
    assert params['$filter'] == 'IsRead eq false'


def test_build_list_query_combines_clauses_with_and():
    params = build_list_query(unread=True, since='2026-04-01', until='2026-04-30')
    assert params['$filter'] == (
        'IsRead eq false'
        ' and ReceivedDateTime ge 2026-04-01T00:00:00Z'
        ' and ReceivedDateTime le 2026-04-30T23:59:59Z'
    )


def test_build_list_query_limit_and_select_passthrough():
    params = build_list_query(limit=5, select='Id,Subject')
    assert params['$top'] == 5
    assert params['$select'] == 'Id,Subject'
