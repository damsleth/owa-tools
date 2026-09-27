"""Capture a short-lived SWODP browser session from an Edge sidecar profile.

Prod runs in the owa-piggy sidecar of the profile that declares the `swodp`
service (one Entra sign-in per account, shared with reseed); UAT, and prod
when no profile declares it, keep a dedicated profile under
~/.config/owa-swodp.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from owa_core.auth import get_profiles
from owa_core.errors import AuthExpiredError, InternalError, OwaError, UsageError

from .cdp import CdpError, CdpSession, find_tab

INSTANCE_HOSTS = {
    "prod": "swodp.service-now.com",
    "uat": "swodpuat.service-now.com",
}
_EDGE_CANDIDATES = (
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/microsoft-edge",
    "/usr/bin/microsoft-edge-stable",
)


@dataclass(frozen=True)
class SwodpSession:
    instance: str
    host: str
    user: str
    user_token: str
    cookie_header: str


def config_root() -> Path:
    override = os.environ.get("OWA_SWODP_CONFIG_DIR", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".config" / "owa-swodp"


SERVICE = "swodp"
# A reseed holds a sidecar for one Edge launch at a time (up to ~80s for a
# slow /token round-trip); wait out one of those, not a whole reseed run.
_LOCK_WAIT = 120.0


def profile_dir(instance: str) -> Path:
    validate_instance(instance)
    if instance == "prod" and not os.environ.get("OWA_SWODP_CONFIG_DIR", "").strip():
        shared = _broker_sidecar()
        if shared is not None:
            return shared
    name = "edge-profile" if instance == "prod" else f"edge-profile-{instance}"
    return config_root() / name


def _broker_sidecar() -> Path | None:
    """The owa-piggy sidecar of the profile whose services include `swodp`.

    That sidecar is already signed in to Entra for the same account, so
    ServiceNow SSOs through it and there is no second sign-in to keep
    alive. None when the broker is unavailable or no profile declares it.
    """
    try:
        rows = get_profiles(tool_name="owa-swodp")
    except OwaError:
        return None
    dirs = [row.edge_dir for row in rows if SERVICE in row.services and row.edge_dir and row.registered]
    if len(dirs) > 1:
        raise UsageError("several owa-piggy profiles declare swodp; keep it on one (OWA_SERVICES)")
    return Path(dirs[0]) if dirs else None


@contextlib.contextmanager
def sidecar_lock(directory: Path):
    """Hold `<directory>/.owa-lock` (exclusive flock) for a whole Edge run.

    The same lock owa-piggy's capture takes on its sidecars: two Edges on
    one --user-data-dir singleton-forward into each other and the second
    never opens its debug port. Wait for a turn rather than failing, as
    the broker does.
    """
    fd = os.open(directory / ".owa-lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + _LOCK_WAIT
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise InternalError(
                        f"the Edge profile at {directory} stayed busy for {_LOCK_WAIT:.0f}s"
                    ) from None
                time.sleep(0.25)
        yield
    finally:
        os.close(fd)


def validate_instance(instance: str) -> str:
    if instance not in INSTANCE_HOSTS:
        raise UsageError(f"unknown SWODP instance: {instance}; choose prod or uat")
    return instance


def find_edge():
    for path in _EDGE_CANDIDATES:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which("microsoft-edge") or shutil.which("msedge")


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def launch_edge(edge_dir, port, *, headless, url):
    binary = find_edge()
    if not binary:
        raise UsageError("Microsoft Edge not found", remediation="Install Microsoft Edge")
    args = [
        binary,
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        # Edge clones its ~1 GB app bundle per launch and only removes it on
        # a clean exit; a killed sidecar leaks one (owa-piggy filled a disk
        # that way). A browser that lives for seconds doesn't need it.
        "--disable-features=MacAppCodeSignClone",
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={edge_dir}",
    ]
    if headless:
        args += ["--headless=new", "--window-position=-32000,-32000", "--window-size=1,1"]
    else:
        args += ["--window-position=100,100", "--window-size=900,750"]
    args.append(url)
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _terminate(process):
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass


def _evaluate_identity(session):
    response = session.call(
        "Runtime.evaluate",
        {
            "expression": (
                "({user: window.NOW?.user_name || window.g_user?.userName || null, "
                "token: window.g_ck || null})"
            ),
            "returnByValue": True,
        },
    )
    return response.get("result", {}).get("value") or {}


def capture(instance="prod", *, visible=False, timeout=45.0, log=None):
    """Launch Edge, wait for an authenticated page, and return cookies + g_ck.

    Credentials remain in memory. The persistent browser profile is the only
    on-disk session store and is separate for prod and UAT.
    """
    validate_instance(instance)
    logger = log or (lambda *_: None)
    directory = profile_dir(instance)
    root = config_root()
    if root in directory.parents:
        # Our own profile dirs only: a broker sidecar is owa-piggy's to create
        # and permission.
        for path in (root, directory):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                path.chmod(0o700)
            except OSError:
                pass
    elif not directory.is_dir():
        raise AuthExpiredError(
            f"owa-piggy sidecar {directory} does not exist",
            remediation="Run: owa-piggy edge --profile <the profile with swodp>",
        )
    with sidecar_lock(directory):
        return _capture_locked(instance, directory, visible=visible, timeout=timeout, logger=logger)


def _capture_locked(instance, directory, *, visible, timeout, logger):
    host = INSTANCE_HOSTS[instance]
    port = find_free_port()
    process = launch_edge(str(directory), port, headless=not visible, url=f"https://{host}/tcp")
    cdp = None
    started = time.monotonic()
    try:
        tab = find_tab(port, timeout=min(15.0, timeout))
        cdp = CdpSession(port, tab["webSocketDebuggerUrl"])
        cdp.call("Runtime.enable")
        cdp.call("Network.enable")
        deadline = started + timeout
        last_tick = started
        identity = {}
        while time.monotonic() < deadline:
            identity = _evaluate_identity(cdp)
            if identity.get("user") not in (None, "", "guest") and identity.get("token"):
                break
            now = time.monotonic()
            if now - last_tick >= 5:
                logger(f"waiting for SWODP sign-in ({int(now - started)}s)")
                last_tick = now
            time.sleep(1)
        else:
            hint = f"Run: owa-swodp setup --instance {instance}"
            raise AuthExpiredError("SWODP browser session is not authenticated", remediation=hint)
        cookies = cdp.call("Network.getCookies", {"urls": [f"https://{host}"]}).get(
            "cookies", []
        )
        cookie_header = "; ".join(
            f"{cookie['name']}={cookie['value']}"
            for cookie in cookies
            if cookie.get("name") and cookie.get("value")
        )
        if not cookie_header:
            raise AuthExpiredError("SWODP returned no session cookies")
        return SwodpSession(
            instance=instance,
            host=host,
            user=str(identity["user"]),
            user_token=str(identity["token"]),
            cookie_header=cookie_header,
        )
    except (AuthExpiredError, UsageError):
        raise
    except (CdpError, ConnectionError, OSError, TimeoutError) as exc:
        raise InternalError(f"could not capture SWODP session: {exc}", cause=exc) from exc
    finally:
        if cdp is not None:
            cdp.close()
        _terminate(process)
