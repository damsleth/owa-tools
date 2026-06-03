"""DASH manifest: build the clear-path URL, fetch, and parse.

The transform service accepts an SPO Bearer access_token in place of the
player's signed P1-P4 params, and omitting `enableEncryption` makes it
return CLEAR (unencrypted) fmp4 segments - no key, no AES, no cookies.
Encrypted manifests (ContentProtection / sea:) are rejected outright;
decryption is explicitly out of scope for this package.
"""
import re
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlsplit

from owa_core.errors import AuthExpiredError, InternalError, NetworkError, UsageError

from . import auth as auth_mod


def build_manifest_url(job, token):
    qs = urlencode({
        "provider": "spo",
        "docId": job.docid,
        "cTag": job.ctag or "",
        "action": "Access",
        "part": "index",
        "format": "dash",
        "access_token": token,
    })
    return f"https://{job.region}/transform/videomanifest?{qs}"


def fetch_manifest(http_client, job, token):
    status, data = http_client.get(build_manifest_url(job, token))
    if status != 200:
        body = data[:200].decode('utf-8', 'replace')
        message = f'manifest fetch failed (HTTP {status}): {body}'
        if status in (401, 403):
            raise AuthExpiredError(message)
        raise NetworkError(message)
    return data.decode("utf-8", "replace")


def _manifest(http_client, job, config, debug):
    """Fetch + parse the manifest. Returns (parsed, token_holder).

    The token_holder dict feeds the segment loop: `token` is the live SPO
    token baked into segment URLs, `refresh` re-mints it once on 401/403.
    """
    token = auth_mod.get_spo_token(config, job.spo_host, debug=debug)
    holder = {
        "token": token,
        "refresh": auth_mod.make_spo_refresh(config, job.spo_host, debug=debug),
    }
    return parse_manifest(fetch_manifest(http_client, job, token)), holder


def _parse_iso_duration(xml):
    """mediaPresentationDuration -> seconds. Handles full ISO-8601 PnDTnHnMnS
    (e.g. PT1H2M3S, PT0H28M34.5S, PT45S), not just the PT0H0M…S shape."""
    m = re.search(r'mediaPresentationDuration="(P[^"]*)"', xml)
    if not m:
        return None
    md = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?)?", m.group(1))
    if not md:
        return None
    days, h, mi, s = md.groups()
    total = (float(days or 0) * 86400 + float(h or 0) * 3600
             + float(mi or 0) * 60 + float(s or 0))
    return total or None


def _expand_timeline(tl_xml, timescale, duration_s):
    """Expand a <SegmentTimeline> into a list of segment start times.

    Handles the open-ended DASH shorthand r="-1" (repeat the segment until the
    next <S>'s t, or the period end derived from the presentation duration)."""
    raw = []
    for s in re.finditer(r"<S\s+([^/>]*)/?>", tl_xml):
        a = dict(re.findall(r'(\w+)="(-?\d+)"', s.group(1)))
        raw.append((int(a["t"]) if "t" in a else None, int(a["d"]), int(a.get("r", 0))))
    period_end = round(duration_s * timescale) if (duration_s and timescale) else None
    times, t = [], 0
    for i, (t0, d, r) in enumerate(raw):
        if t0 is not None:
            t = t0
        if r >= 0:
            for _ in range(r + 1):
                times.append(t)
                t += d
        else:  # r == -1: fill until the next <S> start, else the period end
            nxt = raw[i + 1][0] if (i + 1 < len(raw) and raw[i + 1][0] is not None) else period_end
            if nxt is None:
                raise InternalError(
                    'manifest has an open-ended SegmentTimeline (r=-1) but no '
                    'duration to bound it; cannot enumerate segments'
                )
            while t < nxt:
                times.append(t)
                t += d
    return times


def parse_manifest(xml):
    if "ContentProtection" in xml or "sea:" in xml:
        raise UsageError('manifest came back encrypted; this build expects the clear path')
    base = re.search(r"<BaseURL>([^<]+)</BaseURL>", xml).group(1).strip()
    dur = _parse_iso_duration(xml)
    tracks = {}
    for am in re.finditer(r'<AdaptationSet[^>]*contentType="(\w+)".*?</AdaptationSet>', xml, re.S):
        blk, ctype = am.group(0), am.group(1)
        st = re.search(r"<SegmentTemplate ([^>]*)>", blk).group(1)
        init = unescape(re.search(r'initialization="([^"]+)"', st).group(1))
        media = unescape(re.search(r'media="([^"]+)"', st).group(1))
        tsm = re.search(r'timescale="(\d+)"', st)
        timescale = int(tsm.group(1)) if tsm else None
        rep = re.search(r'<Representation id="([^"]+)"', blk)
        repid = rep.group(1) if rep else ""
        codecs = (re.search(r'codecs="([^"]+)"', blk) or [None, None])[1]
        tl = re.search(r"<SegmentTimeline>(.*?)</SegmentTimeline>", blk, re.S).group(1)
        times = _expand_timeline(tl, timescale, dur)

        def fix(u, repid=repid):
            return u.replace("$RepresentationID$", repid)

        tracks[ctype] = {
            "init": base + fix(init), "media_tmpl": base + fix(media),
            "times": times, "codecs": codecs,
            "width": _intattr(blk, "width"), "height": _intattr(blk, "height"),
        }
    return {"base": base, "duration": dur, "tracks": tracks}


def _intattr(blk, name):
    m = re.search(rf'{name}="(\d+)"', blk)
    return int(m.group(1)) if m else None


def _with_token(url, token):
    sp = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(sp.query, keep_blank_values=True) if k != "access_token"]
    q.append(("access_token", token))
    return f"{sp.scheme}://{sp.netloc}{sp.path}?{urlencode(q)}"
