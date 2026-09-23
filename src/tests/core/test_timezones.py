from datetime import datetime, timedelta, timezone

import pytest

from owa_core.timezones import parse_iso_datetime


@pytest.mark.parametrize('value,expected', [
    ('2026-04-20T09:00:00.123456', datetime(2026, 4, 20, 9, 0, 0, 123456)),
    ('2026-04-20T09:00:00.1234567', datetime(2026, 4, 20, 9, 0, 0, 123456)),
    ('2026-04-20T09:00:00Z', datetime(2026, 4, 20, 9, tzinfo=timezone.utc)),
    ('2026-06-02T08:17:12.4940000Z', datetime(2026, 6, 2, 8, 17, 12, 494000, tzinfo=timezone.utc)),
    (' 2026-01-15T09:00:00.1234567+02:00 ',
     datetime(2026, 1, 15, 9, 0, 0, 123456, tzinfo=timezone(timedelta(hours=2)))),
    ('2026-06-01', datetime(2026, 6, 1)),
])
def test_parse_iso_datetime(value, expected):
    assert parse_iso_datetime(value) == expected


def test_parse_iso_datetime_naive_stays_naive():
    assert parse_iso_datetime('2026-04-20T09:00:00').tzinfo is None


def test_parse_iso_datetime_rejects_garbage():
    with pytest.raises(ValueError):
        parse_iso_datetime('not-a-date')
