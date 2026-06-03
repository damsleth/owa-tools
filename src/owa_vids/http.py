"""Per-host keep-alive HTTP for the svc.ms media CDN.

`owa_core.http.request` rides urllib's urlopen, which opens a fresh
connection per request. The svc.ms transform service throttles reconnects
aggressively during the multi-hundred-segment download loop, so this
module keeps one persistent `http.client.HTTPSConnection` per host and
recycles it only on transient failures. This is the suite's single
sanctioned exception to "all HTTP goes through owa_core.http" - do not
refactor onto urlopen without re-testing against a live svc.ms tenant.
"""
import http.client
import json
import sys
import time
from urllib.parse import urlsplit

from owa_core.errors import AuthExpiredError, NetworkError

UA = ("Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
# Transient/throttle statuses worth an automatic backoff+retry inside Http.get.
# 401/403 are deliberately NOT here: those are returned to the caller so it can
# refresh an expired token (segment download) or fail with context (manifest).
TRANSIENT = {408, 429, 500, 502, 503, 504}


def _info(msg):
    print(msg, file=sys.stderr, flush=True)


def _safe_url(url):
    """Strip the query string (it carries access_token) for error text."""
    sp = urlsplit(url)
    return f'{sp.scheme}://{sp.netloc}{sp.path}'


class Http:
    """One persistent connection per host, throttle-aware."""

    def __init__(self, debug=False):
        self.conns = {}
        self.debug = debug

    def _conn(self, host, fresh=False):
        if fresh and host in self.conns:
            try:
                self.conns[host].close()
            except Exception:
                pass
            self.conns.pop(host, None)
        if host not in self.conns:
            self.conns[host] = http.client.HTTPSConnection(host, timeout=90)
        return self.conns[host]

    def get(self, url, headers=None, *, tries=8):
        """Return (status, body). Retries only genuinely transient statuses and
        connection errors with backoff; every other status (200, 401/403, 404…)
        is handed straight back so the caller can decide (e.g. refresh a token)."""
        headers = dict(headers or {})
        headers.setdefault("User-Agent", UA)
        sp = urlsplit(url)
        host = sp.netloc
        path = sp.path + ("?" + sp.query if sp.query else "")
        status, data, last = None, b"", None
        for attempt in range(tries):
            try:
                self._conn(host).request("GET", path, headers=headers)
                resp = self._conn(host).getresponse()
                data = resp.read()
                status = resp.status
                if status == 200 and data:
                    return status, data
                # Treat a 200 with an empty body as transient (truncated response).
                if status in TRANSIENT or (status == 200 and not data):
                    last = f"HTTP {status} (len {len(data)})"
                    retry_after = resp.getheader("Retry-After")
                    wait = int(retry_after) if (retry_after and retry_after.isdigit()) \
                        else min(60, 1.5 * (2 ** attempt))
                    self._conn(host, fresh=True)
                    if self.debug:
                        _info(f"DEBUG: {last}; backoff {wait:.0f}s")
                    time.sleep(wait)
                    continue
                return status, data  # 401/403/404/… -> caller decides
            except (http.client.HTTPException, OSError) as exc:
                last = repr(exc)
                self._conn(host, fresh=True)
                time.sleep(min(30, 2 ** attempt))
        if status is not None:
            return status, data  # exhausted retries on a transient status
        raise NetworkError(f'request failed after {tries} tries: {last}: {_safe_url(url)}')


def graph_get(http_client, token, url):
    """Authenticated JSON GET via the keep-alive client; raises on non-200."""
    status, data = http_client.get(
        url, {"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    if status != 200:
        body = data[:200].decode('utf-8', 'replace')
        if status in (401, 403):
            raise AuthExpiredError(f'Graph {status}: {body}')
        raise NetworkError(f'Graph {status}: {body}')
    return json.loads(data)
