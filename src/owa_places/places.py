"""Normalize SchedulingB2 meeting-location payloads."""


def _first(*values):
    for value in values:
        if value not in (None, ''):
            return value
    return None


def _address(raw):
    address = raw.get('address') or raw.get('Address') or {}
    if isinstance(address, str):
        return address
    if not isinstance(address, dict):
        return ''
    parts = [
        address.get('street') or address.get('Street'),
        address.get('city') or address.get('City'),
        address.get('state') or address.get('State'),
        address.get('postalCode') or address.get('PostalCode'),
        address.get('countryOrRegion') or address.get('CountryOrRegion'),
    ]
    return ', '.join(str(part) for part in parts if part)


def normalize_location(raw):
    email = _first(
        raw.get('emailAddress'),
        raw.get('EmailAddress'),
        raw.get('smtpAddress'),
        raw.get('SmtpAddress'),
        raw.get('address'),
    )
    return {
        'id': _first(raw.get('id'), raw.get('Id'), raw.get('itemId'), raw.get('ItemId'), email),
        'name': _first(raw.get('displayName'), raw.get('DisplayName'), raw.get('name'), raw.get('Name'), email),
        'email': email,
        'type': _first(raw.get('type'), raw.get('Type'), raw.get('locationType'), raw.get('LocationType'), ''),
        'capacity': _first(raw.get('capacity'), raw.get('Capacity')),
        'address': _address(raw),
        'building': _first(raw.get('building'), raw.get('Building')),
        'floor': _first(raw.get('floor'), raw.get('Floor')),
        'raw': raw,
    }


def _iter_candidates(payload):
    if isinstance(payload, list):
        yield from payload
        return
    if not isinstance(payload, dict):
        return
    for key in (
        'locations',
        'Locations',
        'meetingLocations',
        'MeetingLocations',
        'rooms',
        'Rooms',
        'recentLocations',
        'RecentLocations',
        'value',
    ):
        values = payload.get(key)
        if isinstance(values, list):
            # A SchedulingB2 response uses ONE container key. Stop at the first
            # match so a payload exposing several (e.g. both casings, or a key
            # plus 'value') doesn't yield the same locations more than once.
            yield from values
            return


def normalize_locations(payload):
    rows = []
    for item in _iter_candidates(payload):
        if isinstance(item, dict):
            rows.append(normalize_location(item))
    return rows


def filter_locations(rows, *, query='', rooms_only=False, limit=None):
    if limit is not None and limit <= 0:
        return []
    query = query.lower()
    out = []
    for row in rows:
        haystack = ' '.join(str(row.get(key) or '') for key in ('name', 'email', 'building', 'floor')).lower()
        if query and query not in haystack:
            continue
        if rooms_only and not row.get('email'):
            continue
        out.append(row)
        if limit is not None and len(out) >= limit:
            break
    return out
