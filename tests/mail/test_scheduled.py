"""Tests for scheduled (deferred) send extended property building."""
import pytest

from owa_mail.scheduled import (
    DEFERRED_SEND_PROPERTY_ID,
    build_deferred_send_props,
    to_outlook_utc,
)


def test_property_id_is_pr_deferred_send_time():
    """Locking the MAPI tag in: SystemTime 0x3FEF == PR_DEFERRED_SEND_TIME."""
    assert DEFERRED_SEND_PROPERTY_ID == 'SystemTime 0x3FEF'


def test_to_outlook_utc_passes_through_z_suffix():
    assert to_outlook_utc('2026-05-01T09:00:00Z') == '2026-05-01T09:00:00Z'


def test_to_outlook_utc_naive_assumed_utc():
    assert to_outlook_utc('2026-05-01T09:00:00') == '2026-05-01T09:00:00Z'


def test_to_outlook_utc_converts_offset_to_utc():
    # 09:00+02:00 -> 07:00Z
    assert to_outlook_utc('2026-05-01T09:00:00+02:00') == '2026-05-01T07:00:00Z'


def test_to_outlook_utc_rejects_empty():
    with pytest.raises(ValueError):
        to_outlook_utc('')


def test_to_outlook_utc_rejects_garbage():
    with pytest.raises(ValueError):
        to_outlook_utc('not a date')


def test_build_deferred_send_props_shape():
    props = build_deferred_send_props('2026-05-01T09:00:00Z')
    assert props == [{
        'PropertyId': 'SystemTime 0x3FEF',
        'Value': '2026-05-01T09:00:00Z',
    }]
