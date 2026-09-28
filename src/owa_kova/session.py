"""Read Kova pages through the owa-piggy sidecar that holds the Kova session.

Kova (www.kova.no) is server-rendered ASP.NET that signs in through Okta and
knows the user only by its session cookie. owa-piggy keeps that session alive
in the profile's Edge sidecar (`clients add kova`, renewed on reseed, session
cookies pinned so they outlive Edge). owa-kova does what owa-swodp does for
ServiceNow: take the broker's lock on that sidecar, open it headless, and run
the request inside the page so the browser's own cookies authenticate it.
Nothing is written or printed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from owa_core.auth import get_profiles
from owa_core.errors import AuthExpiredError, InternalError, UsageError

# ponytail: Edge/CDP plumbing borrowed from owa_swodp; move both into owa_core
# if a third sidecar tool shows up.
from owa_swodp.cdp import CdpError, CdpSession, find_tab
from owa_swodp.session import _terminate, find_free_port, launch_edge, sidecar_lock

SERVICE = 'kova'
HOST = 'www.kova.no'
REMEDIATION = 'Run: owa-piggy clients add kova --profile <alias>'


def resolve_sidecar(profile=None):
    """(alias, edge_dir) of the profile with Kova: --profile, else the default
    profile if it has Kova, else the only one."""
    rows = [p for p in get_profiles(tool_name='owa-kova') if p.has_config]
    if profile:
        pick = next((p for p in rows if p.alias == profile), None)
        if pick is None:
            raise UsageError(f'no owa-piggy profile {profile!r}')
    else:
        kova = [p for p in rows if SERVICE in p.services]
        pick = next((p for p in kova if p.default), None) or (kova[0] if len(kova) == 1 else None)
        if pick is None and not kova:
            raise UsageError('no profile has Kova', remediation=REMEDIATION)
        if pick is None:
            raise UsageError(f'several profiles have Kova ({", ".join(p.alias for p in kova)}); '
                             'pick one with --profile')
    if SERVICE not in pick.services or not pick.edge_dir:
        raise AuthExpiredError(f'profile {pick.alias!r} is not signed in to Kova', remediation=REMEDIATION)
    return pick.alias, Path(pick.edge_dir)


def _eval(cdp, expression):
    result = cdp.call('Runtime.evaluate', {'expression': expression, 'awaitPromise': True, 'returnByValue': True})
    if result.get('exceptionDetails'):
        raise InternalError(f'Kova page script failed: {result["exceptionDetails"].get("text", "")}')
    return (result.get('result') or {}).get('value')


def fetch_json(paths, *, profile=None, timeout=30.0, log=None):
    """GET each Kova API path (relative, e.g. '/api/default/GetOpenDuties?...')
    inside the signed-in sidecar and return the decoded JSON bodies in order."""
    logger = log or (lambda *_: None)
    alias, edge_dir = resolve_sidecar(profile)
    if not edge_dir.is_dir():
        raise AuthExpiredError(f'owa-piggy sidecar {edge_dir} does not exist', remediation=REMEDIATION)
    with sidecar_lock(edge_dir):
        port = find_free_port()
        process = launch_edge(str(edge_dir), port, headless=True, url=f'https://{HOST}/Members/Default.aspx')
        cdp = None
        try:
            cdp = CdpSession(port, find_tab(port, timeout=15.0)['webSocketDebuggerUrl'])
            deadline = time.monotonic() + timeout
            here = ''
            while time.monotonic() < deadline:
                here = _eval(cdp, 'location.host') or ''
                if here == HOST and _eval(cdp, 'document.readyState') == 'complete':
                    break
                time.sleep(0.5)
            if here != HOST:
                raise AuthExpiredError(f'Kova session expired (sidecar parked on {here or "a blank page"})',
                                       remediation=REMEDIATION)
            logger(f'Kova session ok in profile {alias}')
            out = []
            for path in paths:
                raw = _eval(cdp, f"fetch({json.dumps(path)}, {{credentials: 'include'}})"
                                 ".then(async r => JSON.stringify([r.status, r.url, await r.text()]))")
                status, url, body = json.loads(raw)
                if HOST not in url:
                    raise AuthExpiredError('Kova redirected the request to sign-in', remediation=REMEDIATION)
                if status != 200:
                    raise InternalError(f'Kova {path.split("?")[0]} returned HTTP {status}')
                out.append(json.loads(body))
            return out
        except (CdpError, ConnectionError, OSError, TimeoutError) as exc:
            raise InternalError(f'could not read Kova through the sidecar: {exc}', cause=exc) from exc
        finally:
            if cdp is not None:
                cdp.close()
            _terminate(process)
