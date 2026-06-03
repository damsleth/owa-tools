"""Segment download loop and ffmpeg mux.

Segments are fetched serially (SharePoint throttles concurrency hard)
with a small inter-segment delay, written atomically via `.part` files
so an interrupted download resumes for free, then concatenated and muxed
with `ffmpeg -c copy`.
"""
import os
import subprocess
import sys
import time
from urllib.parse import urlsplit

from owa_core.errors import InternalError, NetworkError

from .manifest import _with_token

# Serial inter-segment delay. Together with the per-host keep-alive in
# .http this is what keeps the transform service from 429ing the loop.
DELAY = 0.10


def _info(msg):
    print(msg, file=sys.stderr, flush=True)


def download_track(http_client, name, tr, token_holder, workdir, *, limit=None,
                   probe=False, verbose=False):
    os.makedirs(workdir, exist_ok=True)
    n = len(tr["times"]) if limit is None else min(limit, len(tr["times"]))
    seg_urls = [("init", tr["init"])]
    for i in range(n):
        seg_urls.append((f"{i:04d}", tr["media_tmpl"].replace("$Time$", str(tr["times"][i]))))

    done = 0
    for tag, url in seg_urls:
        path = os.path.join(workdir, f"{name}_{tag}.m4s")
        if not (os.path.exists(path) and os.path.getsize(path) > 0):
            data = _get_segment(http_client, url, token_holder)
            if probe:
                head = b"ftyp" if tag == "init" else b"moof"
                if head not in data[:16]:
                    raise InternalError(
                        f'probe: {name}_{tag} is not a valid fMP4 box ({data[:12].hex()})'
                    )
            with open(path + ".part", "wb") as fh:
                fh.write(data)
            os.rename(path + ".part", path)
            time.sleep(DELAY)
        done += 1
        if verbose and (done % 20 == 0 or done == len(seg_urls)):
            _info(f"  {name}: {done}/{len(seg_urls)}")

    out = os.path.join(workdir, f"{name}.m4s")
    with open(out, "wb") as o:
        with open(os.path.join(workdir, f"{name}_init.m4s"), "rb") as fh:
            o.write(fh.read())
        for i in range(n):
            with open(os.path.join(workdir, f"{name}_{i:04d}.m4s"), "rb") as fh:
                o.write(fh.read())
    return out


def _get_segment(http_client, url, token_holder, tries=6):
    """GET a clear segment. On 401/403, mint a fresh token once (the baked-in
    access_token expires ~80 min in) and retry; back off in case the 401 is a
    transient throttle rather than expiry. Http.get already retried 5xx/429."""
    status = None
    refreshed = False
    for attempt in range(tries):
        status, data = http_client.get(_with_token(url, token_holder["token"]))
        if status == 200 and data:
            return data
        if status in (401, 403):
            if not refreshed and token_holder.get("refresh"):
                token_holder["token"] = token_holder["refresh"]()
                refreshed = True
                continue  # retry immediately with the new token
            time.sleep(min(30, 2 ** attempt))  # residual throttle: back off
            continue
        time.sleep(min(15, 2 ** attempt))  # any other non-200: brief retry
    sp = urlsplit(url)
    raise NetworkError(
        f'segment fetch failed (HTTP {status}): {sp.scheme}://{sp.netloc}{sp.path}'
    )


def mux(track_files, out_path, debug=False):
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for name in ("video", "audio"):
        if name in track_files:
            cmd += ["-i", track_files[name]]
    cmd += ["-c", "copy", out_path]
    if debug:
        _info("DEBUG: " + " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InternalError(f'ffmpeg mux failed: {exc}')
