from owa_core.http import Response
from owa_places import api


def test_scheduling_post_uses_pinned_endpoint(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen.update(method=method, url=url, kwargs=kwargs)
        return Response(status=200, headers={}, json={'Locations': []}, bytes=b'{}')

    monkeypatch.setattr(api.http, 'request', fake_request)
    assert api.scheduling_post('https://outlook.office.com', 'tok', {'NumberOfLocations': 5}, cv='cv1') == {'Locations': []}
    assert seen['method'] == 'POST'
    assert seen['url'] == 'https://outlook.office.com/SchedulingB2/api/v1.0/me/initmeetinglocations?cv=cv1'
    assert seen['kwargs']['token'] == 'tok'
    assert seen['kwargs']['body'] == {'NumberOfLocations': 5}
