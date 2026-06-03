"""Source resolution: turn --manifest-url / --embed-url into a Job."""
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


def _resolve(manifest_url, embed_url, region_override, config, debug):
    """Dispatch on the source kind. Exactly one of the URLs must be set."""
    if manifest_url:
        return resolve_manifest_url(manifest_url, config, debug)
    if embed_url:
        return resolve_embed_url(embed_url, config, region_override, debug)
    raise UsageError('need a source: --manifest-url or --embed-url')


def resolve_manifest_url(manifest_url, config, debug):
    """--manifest-url: parse region/docid/ctag straight out of the URL."""
    q = parse_qs(urlsplit(manifest_url).query, keep_blank_values=True)
    region = urlsplit(manifest_url).netloc
    docid_raw = unquote((q.get("docid") or q.get("docId") or [""])[0])
    if not docid_raw:
        raise UsageError('manifest URL has no docid param')
    spo_host = urlsplit(docid_raw).netloc
    ctag = unquote((q.get("cTag") or q.get("ctag") or [""])[0]) or None
    # remember the (tenant-wide) region for later --embed-url runs
    if region and config.get('region') != region:
        config_mod.config_set('region', region)
        config['region'] = region
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
    region = region_override or config.get('region')
    if not region:
        raise UsageError(
            'media region unknown for --embed-url. Run once with --manifest-url '
            '(copied from DevTools) to cache it, or pass --region <host>.'
        )

    http_client = Http(debug)
    spo_tok = auth_mod.get_spo_token(config, spo_host, debug=debug)
    # 1) uniqueId -> server-relative URL + name
    f = graph_get_spo(http_client, spo_tok, spo_host, site, uid)
    server_rel = f["ServerRelativeUrl"]
    web_url = f"https://{spo_host}{quote(server_rel)}"
    # 2) webUrl -> driveId/itemId/cTag via Graph shares (works cross-user)
    gtok = auth_mod.get_graph_token(config, debug=debug)
    share = "u!" + quote(base64.urlsafe_b64encode(web_url.encode()).decode().rstrip("="))
    d = graph_get(http_client, gtok,
                  f"{auth_mod.GRAPH_BASE}/shares/{share}/driveItem"
                  f"?$select=id,name,cTag,parentReference")
    drive_id = (d.get("parentReference") or {}).get("driveId")
    item_id = d.get("id")
    if not (drive_id and item_id):
        raise NotFoundError('could not resolve driveId/itemId from the embed URL')
    docid = (f"https://{spo_host}{site}/_api/v2.0/drives/{drive_id}"
             f"/items/{item_id}?version=Published")
    return Job(spo_host=spo_host, docid=docid, ctag=d.get("cTag"), region=region,
               title=d.get("name") or f.get("Name"), drive_id=drive_id, item_id=item_id)


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
