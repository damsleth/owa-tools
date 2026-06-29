"""Source resolution: turn a pasted recording URL into a Job."""
import base64
import json
import re
from urllib.parse import parse_qs, quote, unquote, urlsplit

from owa_core.errors import (
    AuthExpiredError,
    NetworkError,
    NotFoundError,
    OwaError,
    UsageError,
)

from . import auth as auth_mod
from . import config as config_mod
from .http import Http, graph_get


class Job:
    """Everything needed to build a manifest URL and name the output."""

    def __init__(self, *, spo_host, docid, ctag, region, title=None,
                 drive_id=None, item_id=None):
        self.spo_host = spo_host
        self.docid = docid        # SPO item API URL ending in ?version=Published
        self.ctag = ctag
        self.region = region      # *-mediap.svc.ms host
        self.title = title
        self.drive_id = drive_id
        self.item_id = item_id


def _docid_base(docid):
    """Strip signed/extra params, keep the bare item URL + version=Published."""
    base = docid.split("?", 1)[0]
    return base + "?version=Published"


def _resolve(manifest_url, embed_url, source_url, region_override, config, debug):
    """Dispatch on the source kind. Exactly one of the URLs must be set."""
    if manifest_url:
        return resolve_manifest_url(manifest_url, config, debug)
    if embed_url:
        return resolve_embed_url(embed_url, config, region_override, debug)
    if source_url:
        return resolve_url(source_url, config, region_override, debug)
    raise UsageError('need a source: paste a recording URL '
                     '(or use --manifest-url / --embed-url)')


def resolve_url(url, config, region_override, debug):
    """Auto-detect a pasted recording URL and route to the right resolver.

    Accepts the videomanifest URL (full source of truth, also caches the
    media region) or any SharePoint URL that names the file: the Stream
    "watch in browser" page (stream.aspx?id=<server-rel path>), the "Copy
    link" sharing URL (.../:v:/r/...), or the embed page (uniqueId). All
    but the manifest URL need the cached/explicit media region.
    """
    low = url.lower()
    if 'videomanifest' in low:
        return resolve_manifest_url(url, config, debug)
    if 'uniqueid=' in low:
        return resolve_embed_url(url, config, region_override, debug)
    return _job_from_shares(_share_target(url), config, region_override, debug)


def _share_target(url):
    """The URL to hand to Graph /shares for a non-manifest source.

    A sharing link (".../:v:/r/...?<token>") is handed over verbatim - Graph
    accepts the whole signed link. A stream.aspx watch page carries the
    server-relative file path in its `id` param; rebuild the file webUrl from
    it, which /shares accepts just as well.
    """
    sp = urlsplit(url)
    if 'stream.aspx' in sp.path.lower():
        sid = unquote((parse_qs(sp.query).get('id') or [''])[0])
        if not sid:
            raise UsageError('stream URL has no id param')
        return f"https://{sp.netloc}{quote(sid)}"
    return url


def resolve_manifest_url(manifest_url, config, debug):
    """--manifest-url: parse region/docid/ctag straight out of the URL."""
    q = parse_qs(urlsplit(manifest_url).query, keep_blank_values=True)
    region = urlsplit(manifest_url).netloc
    docid_raw = unquote((q.get("docid") or q.get("docId") or [""])[0])
    if not docid_raw:
        raise UsageError('manifest URL has no docid param')
    spo_host = urlsplit(docid_raw).netloc
    ctag = unquote((q.get("cTag") or q.get("ctag") or [""])[0]) or None
    # remember the region for this profile so later runs skip discovery
    if region and config_mod.get_region(config) != region:
        config_mod.set_region(config, region)
    job = Job(spo_host=spo_host, docid=_docid_base(docid_raw), ctag=ctag, region=region)
    _attach_drive_item(job)
    if job.drive_id and not job.title:
        _fetch_title(job, config, debug)
    return job


def _attach_drive_item(job):
    m = re.search(r"/drives/([^/]+)/items/([^/?]+)", job.docid)
    if m:
        job.drive_id, job.item_id = m.group(1), m.group(2)


def _fetch_title(job, config, debug):
    """Best-effort: resolve the item's display name (and cTag) via Graph."""
    try:
        http_client = Http(debug)
        gtok = auth_mod.get_graph_token(config, debug=debug)
        d = graph_get(http_client, gtok,
                      f"{auth_mod.GRAPH_BASE}/drives/{job.drive_id}"
                      f"/items/{job.item_id}?$select=name,cTag")
    except OwaError:
        return  # title is best-effort
    job.title = d.get("name")
    if not job.ctag:
        job.ctag = d.get("cTag")


def resolve_embed_url(embed_url, config, region_override, debug):
    """--embed-url: GetFileById(uniqueId) -> webUrl -> Graph /shares -> ids+cTag."""
    sp = urlsplit(embed_url)
    spo_host = sp.netloc
    q = parse_qs(sp.query)
    uid = (q.get("uniqueId") or q.get("uniqueid") or [""])[0]
    if not uid:
        raise UsageError('embed URL has no uniqueId param')
    site = re.sub(r"/_layouts/.*$", "", sp.path)  # /personal/<user>
    http_client = Http(debug)
    spo_tok = auth_mod.get_spo_token(config, spo_host, debug=debug)
    # uniqueId -> server-relative URL, then hand the file webUrl to /shares.
    f = graph_get_spo(http_client, spo_tok, spo_host, site, uid)
    web_url = f"https://{spo_host}{quote(f['ServerRelativeUrl'])}"
    return _job_from_shares(web_url, config, region_override, debug)


def _personal_site(path):
    """/personal/<user>/... or /sites/<site>/... -> the site path, else ''."""
    parts = [p for p in path.split('/') if p]
    if len(parts) >= 2 and parts[0] in ('personal', 'sites', 'teams'):
        return f'/{parts[0]}/{parts[1]}'
    return ''


def _job_from_shares(target_url, config, region_override, debug):
    """Graph /shares on a webUrl or sharing link -> driveId/itemId/cTag Job.

    The media region is taken from --region, then the per-profile cache, then
    auto-discovered from the item's thumbnails (and cached) - so no DevTools
    manifest grab is needed even on the first run.
    """
    spo_host = urlsplit(target_url).netloc
    http_client = Http(debug)
    gtok = auth_mod.get_graph_token(config, debug=debug)
    share = "u!" + quote(base64.urlsafe_b64encode(target_url.encode()).decode().rstrip("="))
    d = graph_get(http_client, gtok,
                  f"{auth_mod.GRAPH_BASE}/shares/{share}/driveItem"
                  f"?$select=id,name,cTag,parentReference,webUrl")
    drive_id = (d.get("parentReference") or {}).get("driveId")
    item_id = d.get("id")
    if not (drive_id and item_id):
        raise NotFoundError('could not resolve driveId/itemId from the URL')
    region = (region_override or config_mod.get_region(config)
              or _discover_region(http_client, gtok, drive_id, item_id, config))
    site = _personal_site(urlsplit(d.get("webUrl") or "").path)
    docid = (f"https://{spo_host}{site}/_api/v2.0/drives/{drive_id}"
             f"/items/{item_id}?version=Published")
    return Job(spo_host=spo_host, docid=docid, ctag=d.get("cTag"), region=region,
               title=d.get("name"), drive_id=drive_id, item_id=item_id)


# The transform service that streams the media; its host is the geo-specific
# media region we need. Item thumbnails are served from that same host.
_MEDIAP_RE = re.compile(r'https://([a-z0-9-]+-mediap\.svc\.ms)')


def _discover_region(http_client, gtok, drive_id, item_id, config):
    """Learn (and cache) the *-mediap.svc.ms region from the item thumbnails."""
    d = graph_get(http_client, gtok,
                  f"{auth_mod.GRAPH_BASE}/drives/{drive_id}/items/{item_id}/thumbnails")
    m = _MEDIAP_RE.search(json.dumps(d))
    if not m:
        raise UsageError(
            'could not auto-detect the media region for this recording; '
            'pass --region <host> (e.g. switzerlandwest1-mediap.svc.ms)'
        )
    region = m.group(1)
    config_mod.set_region(config, region)
    return region


def graph_get_spo(http_client, spo_tok, spo_host, site, uid):
    """SPO REST GetFileById on the personal site, odata=nometadata."""
    sel = quote("Name,UniqueId,ServerRelativeUrl,Length")
    url = f"https://{spo_host}{site}/_api/web/GetFileById(guid'{uid}')?$select={sel}"
    status, data = http_client.get(url, {"Authorization": "Bearer " + spo_tok,
                                         "Accept": "application/json;odata=nometadata"})
    if status != 200:
        body = data[:200].decode('utf-8', 'replace')
        if status in (401, 403):
            raise AuthExpiredError(f'SPO GetFileById {status}: {body}')
        raise NetworkError(f'SPO GetFileById {status}: {body}')
    return json.loads(data)
