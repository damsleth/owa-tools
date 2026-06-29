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
        resolve_mod.config_mod, 'set_region',
        lambda config, region: written.append(region),
    )

    resolve_mod.resolve_manifest_url(MANIFEST_URL, {}, debug=False)

    assert written == ['swon-mediap.svc.ms']


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


def test_resolve_embed_url_auto_discovers_region_when_uncached(monkeypatch):
    monkeypatch.setattr(resolve_mod.auth_mod, 'get_spo_token', lambda *a, **k: 'spo-tok')
    monkeypatch.setattr(resolve_mod.auth_mod, 'get_graph_token', lambda *a, **k: 'graph-tok')
    monkeypatch.setattr(
        resolve_mod, 'graph_get_spo',
        lambda *a: {'ServerRelativeUrl': '/personal/u/Documents/rec.mp4'})

    def fake_graph_get(http_client, tok, url):
        if '/thumbnails' in url:
            return {'value': [{'large': {
                'url': 'https://swedencentral1-mediap.svc.ms/transform/thumbnail?x=1'}}]}
        return {'id': '01ITEM', 'name': 'rec.mp4', 'cTag': 'ct',
                'parentReference': {'driveId': 'b!DRV'}}

    monkeypatch.setattr(resolve_mod, 'graph_get', fake_graph_get)
    saved = []
    monkeypatch.setattr(resolve_mod.config_mod, 'set_region',
                        lambda config, region: saved.append(region))

    embed = ('https://contoso-my.sharepoint.com/personal/u/_layouts/15/'
             'embed.aspx?uniqueId=GUID-1')
    job = resolve_mod.resolve_embed_url(embed, {}, region_override='', debug=False)

    assert job.region == 'swedencentral1-mediap.svc.ms'
    assert saved == ['swedencentral1-mediap.svc.ms']  # cached for next time


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
    out = resolve_mod._resolve('', 'https://h/embed.aspx?uniqueId=g', '', 'r1', {}, debug=False)
    assert out == 'job'
    assert seen == [('https://h/embed.aspx?uniqueId=g', 'r1')]


def test_resolve_dispatches_source_url(monkeypatch):
    seen = []
    monkeypatch.setattr(
        resolve_mod, 'resolve_url',
        lambda url, config, region, debug: seen.append((url, region)) or 'job',
    )
    out = resolve_mod._resolve('', '', 'https://h/x/stream.aspx?id=%2Fa', 'r1', {}, debug=False)
    assert out == 'job'
    assert seen == [('https://h/x/stream.aspx?id=%2Fa', 'r1')]


def test_resolve_requires_a_source():
    with pytest.raises(UsageError):
        resolve_mod._resolve('', '', '', '', {}, debug=False)


def test_resolve_url_routes_manifest(monkeypatch):
    monkeypatch.setattr(resolve_mod, 'resolve_manifest_url',
                        lambda url, config, debug: 'manifest-job')
    out = resolve_mod.resolve_url(MANIFEST_URL, {}, '', debug=False)
    assert out == 'manifest-job'


def test_resolve_url_stream_page_builds_weburl(monkeypatch):
    seen = []
    monkeypatch.setattr(resolve_mod, '_job_from_shares',
                        lambda target, config, region_override, debug:
                        seen.append((target, region_override)) or 'j')
    stream = ('https://contoso-my.sharepoint.com/personal/u/_layouts/15/stream.aspx'
              '?id=%2Fpersonal%2Fu%2FDocuments%2FRecordings%2Frec.mp4&referrer=Teams')
    out = resolve_mod.resolve_url(stream, {}, 'r-override', debug=False)
    assert out == 'j'
    target, region_override = seen[0]
    assert target == ('https://contoso-my.sharepoint.com'
                      '/personal/u/Documents/Recordings/rec.mp4')
    assert region_override == 'r-override'  # --region passed straight through


def test_resolve_url_stream_page_without_id_raises():
    stream = 'https://contoso-my.sharepoint.com/personal/u/_layouts/15/stream.aspx?foo=bar'
    with pytest.raises(UsageError):
        resolve_mod.resolve_url(stream, {'region': 'r'}, '', debug=False)


def test_resolve_url_sharing_link_passed_verbatim(monkeypatch):
    seen = []
    monkeypatch.setattr(resolve_mod, '_job_from_shares',
                        lambda target, config, region, debug: seen.append(target) or 'j')
    link = 'https://contoso-my.sharepoint.com/:v:/r/personal/u/Documents/rec.mp4?csf=1&web=1&e=x'
    resolve_mod.resolve_url(link, {'region': 'r'}, '', debug=False)
    assert seen == [link]


def test_resolve_url_uniqueid_routes_embed(monkeypatch):
    seen = []
    monkeypatch.setattr(resolve_mod, 'resolve_embed_url',
                        lambda url, config, region, debug: seen.append(url) or 'j')
    embed = 'https://contoso-my.sharepoint.com/personal/u/_layouts/15/embed.aspx?uniqueId=G'
    resolve_mod.resolve_url(embed, {'region': 'r'}, '', debug=False)
    assert seen == [embed]


def test_job_from_shares_builds_docid_with_site(monkeypatch):
    monkeypatch.setattr(resolve_mod.auth_mod, 'get_graph_token', lambda *a, **k: 'gtok')
    monkeypatch.setattr(resolve_mod, 'Http', lambda debug: object())
    monkeypatch.setattr(resolve_mod, 'graph_get', lambda *a: {
        'id': '01ITEM', 'name': 'rec.mp4', 'cTag': 'ct',
        'parentReference': {'driveId': 'b!DRV'},
        'webUrl': 'https://contoso-my.sharepoint.com/personal/u/Documents/rec.mp4',
    })
    job = resolve_mod._job_from_shares(
        'https://contoso-my.sharepoint.com/personal/u/Documents/rec.mp4',
        {}, 'r', debug=False)
    assert job.drive_id == 'b!DRV'
    assert job.item_id == '01ITEM'
    assert job.title == 'rec.mp4'
    assert '/personal/u/_api/v2.0/drives/b!DRV/items/01ITEM' in job.docid
    assert job.docid.endswith('?version=Published')


def test_discover_region_extracts_and_caches_host(monkeypatch):
    monkeypatch.setattr(resolve_mod, 'graph_get', lambda *a: {'value': [
        {'small': {'url': 'https://norwayeast1-mediap.svc.ms/transform/thumb?a=1'}}]})
    saved = []
    monkeypatch.setattr(resolve_mod.config_mod, 'set_region',
                        lambda config, region: saved.append(region))
    region = resolve_mod._discover_region(object(), 'gtok', 'b!D', '01I', {})
    assert region == 'norwayeast1-mediap.svc.ms'
    assert saved == ['norwayeast1-mediap.svc.ms']


def test_discover_region_no_host_raises(monkeypatch):
    monkeypatch.setattr(resolve_mod, 'graph_get', lambda *a: {'value': []})
    with pytest.raises(UsageError):
        resolve_mod._discover_region(object(), 'gtok', 'b!D', '01I', {})


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
