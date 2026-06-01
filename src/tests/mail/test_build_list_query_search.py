"""Tests for the search-400 fix in build_list_query.

$search and $orderby are mutually exclusive in Outlook/Graph; sending both
returns HTTP 400. These tests verify that the fix is in place and that
non-search code paths are unaffected.
"""
from owa_mail.messages import LIST_SELECT, build_list_query


def test_search_removes_orderby():
    """(a) build_list_query(search=...) must have $search and NO $orderby."""
    params = build_list_query(search='budget')
    assert '$search' in params, '$search must be present when search is given'
    assert '$orderby' not in params, (
        '$orderby must be absent when $search is set (Outlook/Graph 400 otherwise)'
    )


def test_search_value_is_double_quoted():
    """$search value must be wrapped in double-quotes per Outlook REST convention."""
    params = build_list_query(search='quarterly report')
    assert params['$search'] == '"quarterly report"'


def test_search_result_has_no_filter():
    """$search and $filter are also mutually exclusive; verify $filter is absent."""
    params = build_list_query(search='invoice')
    assert '$filter' not in params


def test_unfiltered_has_orderby():
    """(b) Unfiltered call (no search/sender/subject) must still include $orderby."""
    params = build_list_query()
    assert params['$orderby'] == 'ReceivedDateTime desc'


def test_unfiltered_defaults():
    """Unfiltered call includes expected defaults."""
    params = build_list_query()
    assert params['$top'] == 25
    assert params['$select'] == LIST_SELECT
    assert '$search' not in params
    assert '$filter' not in params


def test_sender_filter_drops_orderby():
    """(c) sender filter path: $orderby must be absent (InefficientFilter risk)."""
    params = build_list_query(sender='alice@example.com')
    assert '$orderby' not in params
    assert '$filter' in params
    assert 'alice@example.com' in params['$filter']
    assert '$search' not in params


def test_subject_filter_drops_orderby():
    """(c) subject filter path: $orderby must be absent."""
    params = build_list_query(subject_q='quarterly')
    assert '$orderby' not in params
    assert "contains(Subject,'quarterly')" in params['$filter']
    assert '$search' not in params


def test_sender_filter_escapes_single_quote():
    """(c) sender filter path: single quotes in address are escaped."""
    params = build_list_query(sender="O'Brien@example.com")
    assert "'O''Brien@example.com'" in params['$filter']


def test_unread_filter_keeps_orderby():
    """unread-only filter (no sender/subject) must retain $orderby."""
    params = build_list_query(unread=True)
    assert params['$orderby'] == 'ReceivedDateTime desc'
    assert params['$filter'] == 'IsRead eq false'


def test_search_empty_string_is_not_search():
    """Empty string for search is falsy; should not set $search or drop $orderby."""
    params = build_list_query(search='')
    assert '$search' not in params
    assert params['$orderby'] == 'ReceivedDateTime desc'
