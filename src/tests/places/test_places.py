from owa_places import places


def test_normalize_locations_accepts_scheduling_shapes():
    rows = places.normalize_locations({
        'Locations': [{
            'DisplayName': 'Room A',
            'EmailAddress': 'room-a@example.com',
            'Capacity': 8,
            'Building': 'HQ',
            'Floor': '3',
            'Address': {'City': 'Oslo', 'CountryOrRegion': 'NO'},
        }]
    })
    assert rows[0]['name'] == 'Room A'
    assert rows[0]['email'] == 'room-a@example.com'
    assert rows[0]['capacity'] == 8
    assert rows[0]['address'] == 'Oslo, NO'


def test_filter_locations_query_rooms_and_limit():
    rows = [
        {'name': 'Room A', 'email': 'room-a@example.com', 'building': 'HQ', 'floor': '3'},
        {'name': 'Cafe', 'email': None, 'building': 'HQ', 'floor': '1'},
    ]
    assert places.filter_locations(rows, query='room', rooms_only=True, limit=1) == [rows[0]]
