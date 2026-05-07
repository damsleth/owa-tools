"""Scheduled (deferred) send support via PR_DEFERRED_SEND_TIME.

Exchange Transport honours the `PR_DEFERRED_SEND_TIME` MAPI property
(`SystemTime 0x3FEF`) server-side: a draft posted with this property
sits in the sender's Outbox until the deferred time, then dispatches.
This is exactly what OWA's "Schedule send" button does.

We expose it via Outlook REST's SingleValueExtendedProperties channel.
The `PropertyId` syntax is `<type> 0x<hex-tag>`.
"""
from datetime import datetime, timezone

DEFERRED_SEND_PROPERTY_ID = 'SystemTime 0x3FEF'


def to_outlook_utc(value):
    """Normalise an ISO datetime to the UTC `YYYY-MM-DDTHH:MM:SSZ`
    shape Outlook REST expects on extended-property values.

    Accepts:
    - naive ISO strings (assumed UTC)
    - timezone-aware ISO strings (converted to UTC)
    - already-Z-suffixed strings (passed through after re-parse)
    """
    if not value:
        raise ValueError('--send-at requires an ISO datetime value')
    raw = value.strip()
    # datetime.fromisoformat doesn't grok the trailing Z on <3.11; swap
    # for a +00:00 before parsing so Python 3.8/3.9/3.10 are happy.
    iso = raw.replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError as e:
        raise ValueError(f'invalid --send-at value: {value} ({e})')
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def build_deferred_send_props(send_at_iso):
    """Build the SingleValueExtendedProperties list payload that pins
    a draft's deferred send time. Returns a list with one entry, the
    shape Outlook REST expects when nested under a `Message` body.
    """
    return [{
        'PropertyId': DEFERRED_SEND_PROPERTY_ID,
        'Value': to_outlook_utc(send_at_iso),
    }]
