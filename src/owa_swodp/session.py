"""Capture a short-lived SWODP browser session from a dedicated Edge profile."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from owa_core.errors import AuthExpiredError, InternalError, UsageError

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


def profile_dir(instance: str) -> Path:
    validate_instance(instance)
    name = "edge-profile" if instance == "prod" else f"edge-profile-{instance}"
    return config_root() / name


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


def launch_edge(edge_dir, port, *, headless, url, edge_path=None):
    binary = edge_path or find_edge()
    if not binary:
        raise UsageError("Microsoft Edge not found", remediation="Install Microsoft Edge")
    args = [
        binary,
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
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


def capture(instance="prod", *, visible=False, timeout=45.0, edge_path=None, log=None):
    """Launch Edge, wait for an authenticated page, and return cookies + g_ck.

    Credentials remain in memory. The persistent browser profile is the only
    on-disk session store and is separate for prod and UAT.
    """
    validate_instance(instance)
    logger = log or (lambda *_: None)
    root = config_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    directory = profile_dir(instance)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    host = INSTANCE_HOSTS[instance]
    port = find_free_port()
    process = launch_edge(
        str(directory), port, headless=not visible, url=f"https://{host}/tcp", edge_path=edge_path
    )
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
