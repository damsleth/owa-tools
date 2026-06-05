"""Source resolution tests - network and broker boundaries mocked."""
from urllib.parse import quote

import pytest

from owa_core.errors import UsageError
from owa_vids import resolve as resolve_mod

DOCID = ('https://contoso-my.sharepoint.com/personal/u/_api/v2.0'
         '/drives/b!abc/items/01XYZ?tempauth=sig')
MANIFEST_URL = (
    'https://swon-mediap.svc.ms/transform/videomanifest'
    f'?docid={quote(DOCID, safe="")}&cTag=%22c%3Atag1%22&format=dash'
)


def test_resolve_manifest_url_parses_docid_region_ctag(monkeypatch):
    monkeypatch.setattr(resolve_mod, '_fetch_title', lambda *a, **k: None)
    monkeypatch.setattr(resolve_mod.config_mod, 'config_set', lambda *a: None)

    job = resolve_mod.resolve_manifest_url(MANIFEST_URL, {}, debug=False)

    assert job.spo_host == 'contoso-my.sharepoint.com'
    assert job.region == 'swon-mediap.svc.ms'
    assert job.docid.endswith('?version=Published')
    assert 'tempauth' not in job.docid
    assert job.ctag == '"c:tag1"'
    assert job.drive_id == 'b!abc'
    assert job.item_id == '01XYZ'


def test_resolve_manifest_url_caches_region(monkeypatch):
    written = []
    monkeypatch.setattr(resolve_mod, '_fetch_title', lambda *a, **k: None)
    monkeypatch.setattr(
        resolve_mod.config_mod, 'config_set',
        lambda key, value: written.append((key, value)),
    )

    config = {}
    resolve_mod.resolve_manifest_url(MANIFEST_URL, config, debug=False)

    assert written == [('region', 'swon-mediap.svc.ms')]
    assert config['region'] == 'swon-mediap.svc.ms'


def test_resolve_manifest_url_skips_cache_when_region_unchanged(monkeypatch):
    written = []
    monkeypatch.setattr(resolve_mod, '_fetch_title', lambda *a, **k: None)
    monkeypatch.setattr(
        resolve_mod.config_mod, 'config_set',
        lambda key, value: written.append((key, value)),
    )

    resolve_mod.resolve_manifest_url(
        MANIFEST_URL, {'region': 'swon-mediap.svc.ms'}, debug=False,
    )

    assert written == []


def test_resolve_manifest_url_without_docid_raises():
    with pytest.raises(UsageError):
        resolve_mod.resolve_manifest_url(
            'https://swon-mediap.svc.ms/transform/videomanifest?format=dash',
            {}, debug=False,
        )


def test_resolve_embed_url_calls_spo_and_graph(monkeypatch):
    monkeypatch.setattr(resolve_mod.auth_mod, 'get_spo_token', lambda *a, **k: 'spo-tok')
    monkeypatch.setattr(resolve_mod.auth_mod, 'get_graph_token', lambda *a, **k: 'graph-tok')

    spo_calls = []

    def fake_graph_get_spo(http_client, tok, host, site, uid):
        spo_calls.append((tok, host, site, uid))
        return {'ServerRelativeUrl': '/personal/u/Documents/rec.mp4', 'Name': 'rec.mp4'}

    graph_calls = []

    def fake_graph_get(http_client, tok, url):
        graph_calls.append((tok, url))
        return {'id': '01ITEM', 'name': 'rec.mp4', 'cTag': 'ct',
                'parentReference': {'driveId': 'b!DRV'}}

    monkeypatch.setattr(resolve_mod, 'graph_get_spo', fake_graph_get_spo)
    monkeypatch.setattr(resolve_mod, 'graph_get', fake_graph_get)

    embed = ('https://contoso-my.sharepoint.com/personal/u/_layouts/15/'
             'embed.aspx?uniqueId=GUID-1')
    job = resolve_mod.resolve_embed_url(
        embed, {'region': 'swon-mediap.svc.ms'}, region_override='', debug=False,
    )

    assert spo_calls == [('spo-tok', 'contoso-my.sharepoint.com', '/personal/u', 'GUID-1')]
    assert graph_calls[0][0] == 'graph-tok'
    assert '/shares/u!' in graph_calls[0][1]
    assert job.drive_id == 'b!DRV'
    assert job.item_id == '01ITEM'
    assert job.title == 'rec.mp4'
    assert job.region == 'swon-mediap.svc.ms'
    assert '/drives/b!DRV/items/01ITEM' in job.docid


def test_resolve_embed_url_missing_region_raises_usage_error():
    embed = ('https://contoso-my.sharepoint.com/personal/u/_layouts/15/'
             'embed.aspx?uniqueId=GUID-1')
    with pytest.raises(UsageError):
        resolve_mod.resolve_embed_url(embed, {}, region_override='', debug=False)


def test_resolve_embed_url_missing_unique_id_raises_usage_error():
    embed = 'https://contoso-my.sharepoint.com/personal/u/_layouts/15/embed.aspx'
    with pytest.raises(UsageError):
        resolve_mod.resolve_embed_url(
            embed, {'region': 'r'}, region_override='', debug=False,
        )


def test_resolve_dispatches_embed_url(monkeypatch):
    seen = []
    monkeypatch.setattr(
        resolve_mod, 'resolve_embed_url',
        lambda url, config, region, debug: seen.append((url, region)) or 'job',
    )
    out = resolve_mod._resolve('', 'https://h/embed.aspx?uniqueId=g', 'r1', {}, debug=False)
    assert out == 'job'
    assert seen == [('https://h/embed.aspx?uniqueId=g', 'r1')]


def test_resolve_requires_a_source():
    with pytest.raises(UsageError):
        resolve_mod._resolve('', '', '', {}, debug=False)


def test_resolve_embed_url_missing_ids_raises_not_found(monkeypatch):
    from owa_core.errors import NotFoundError
    monkeypatch.setattr(resolve_mod.auth_mod, 'get_spo_token', lambda *a, **k: 'spo-tok')
    monkeypatch.setattr(resolve_mod.auth_mod, 'get_graph_token', lambda *a, **k: 'graph-tok')
    monkeypatch.setattr(
        resolve_mod, 'graph_get_spo',
        lambda *a: {'ServerRelativeUrl': '/personal/u/Documents/rec.mp4'},
    )
    monkeypatch.setattr(resolve_mod, 'graph_get', lambda *a: {'id': None})

    embed = ('https://contoso-my.sharepoint.com/personal/u/_layouts/15/'
             'embed.aspx?uniqueId=GUID-1')
    with pytest.raises(NotFoundError):
        resolve_mod.resolve_embed_url(embed, {'region': 'r'}, region_override='', debug=False)


def test_fetch_title_sets_title_and_ctag(monkeypatch):
    monkeypatch.setattr(resolve_mod.auth_mod, 'get_graph_token', lambda *a, **k: 'graph-tok')
    monkeypatch.setattr(resolve_mod, 'Http', lambda debug: object())
    monkeypatch.setattr(
        resolve_mod, 'graph_get', lambda *a: {'name': 'rec.mp4', 'cTag': 'ct-new'},
    )
    job = resolve_mod.Job(spo_host='h', docid='d', ctag=None, region='r',
                          drive_id='b!D', item_id='01I')
    resolve_mod._fetch_title(job, {}, debug=False)
    assert job.title == 'rec.mp4'
    assert job.ctag == 'ct-new'


def test_fetch_title_keeps_existing_ctag(monkeypatch):
    monkeypatch.setattr(resolve_mod.auth_mod, 'get_graph_token', lambda *a, **k: 'graph-tok')
    monkeypatch.setattr(resolve_mod, 'Http', lambda debug: object())
    monkeypatch.setattr(
        resolve_mod, 'graph_get', lambda *a: {'name': 'rec.mp4', 'cTag': 'ct-new'},
    )
    job = resolve_mod.Job(spo_host='h', docid='d', ctag='ct-orig', region='r',
                          drive_id='b!D', item_id='01I')
    resolve_mod._fetch_title(job, {}, debug=False)
    assert job.ctag == 'ct-orig'


def test_fetch_title_is_best_effort(monkeypatch):
    from owa_core.errors import AuthExpiredError

    def boom(*a, **k):
        raise AuthExpiredError('no broker')

    monkeypatch.setattr(resolve_mod.auth_mod, 'get_graph_token', boom)
    job = resolve_mod.Job(spo_host='h', docid='d', ctag=None, region='r',
                          drive_id='b!D', item_id='01I')
    resolve_mod._fetch_title(job, {}, debug=False)  # must not raise
    assert job.title is None


class StubHttp:
    def __init__(self, status, body):
        self.status, self.body = status, body
        self.calls = []

    def get(self, url, headers=None, *, tries=8):
        self.calls.append((url, dict(headers or {})))
        return self.status, self.body


def test_graph_get_spo_builds_getfilebyid_url():
    stub = StubHttp(200, b'{"Name": "rec.mp4"}')
    out = resolve_mod.graph_get_spo(stub, 'spo-tok', 'host', '/personal/u', 'GUID-1')
    assert out == {'Name': 'rec.mp4'}
    url, headers = stub.calls[0]
    assert "GetFileById(guid'GUID-1')" in url
    assert url.startswith('https://host/personal/u/_api/web/')
    assert headers['Authorization'] == 'Bearer spo-tok'
    assert 'odata=nometadata' in headers['Accept']


def test_graph_get_spo_401_raises_auth_expired():
    from owa_core.errors import AuthExpiredError
    with pytest.raises(AuthExpiredError):
        resolve_mod.graph_get_spo(StubHttp(403, b'denied'), 't', 'h', '/s', 'g')


def test_graph_get_spo_500_raises_network_error():
    from owa_core.errors import NetworkError
    with pytest.raises(NetworkError):
        resolve_mod.graph_get_spo(StubHttp(500, b'oops'), 't', 'h', '/s', 'g')
