"""Localhost daemon: the SWODPal app's bridge without the browser extension.

`owa-swodp serve` answers the same `{type, ...}` -> response wire protocol as
the extension's background worker (swodp-enrichment `extension/background.js`),
so the built app only needs a third transport (plain fetch to `/bridge`).
Calendar comes from an owa-piggy Outlook token, SWODP data from this package's
own headless Edge session. Personal use: one user, one laptop.

Any web page can reach 127.0.0.1, so the guards are not optional: the Host
header must be ours (DNS rebinding), a present Origin must be ours, and
`/bridge` POSTs must be `application/json` (a cross-origin page cannot send
that without a preflight, which this daemon never approves - it sends no CORS
headers at all). Tokens and cookies stay in this process and never appear in a
response or a log line.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import sys
import threading
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from owa_core import http
from owa_core.auth import get_profiles, get_token
from owa_core.errors import AuthExpiredError, OwaError, UsageError
from owa_core.secrets import redact

from . import service
from . import session as session_mod

# Keep equal to EXPECTED_BRIDGE_VERSION in the app's swodpBridge.ts; a mismatch
# makes the app show "outdated bridge".
EXPECTED_BRIDGE_VERSION = "0.30.0"
# The extension reads Graph /me/calendarView with its own Calendars.Read app.
# owa-piggy's borrowed OWA client has no Calendars scope on the Graph audience
# (403) but carries Calendars.ReadWrite on the Outlook audience, so the same
# window is read from Outlook REST and reshaped to the Graph form the app parses.
CALENDAR_VIEW = "https://outlook.office.com/api/v2.0/me/calendarview"
CALENDAR_SELECT = "Subject,Start,End,Categories,ShowAs,IsAllDay,Sensitivity,Attendees"
MAX_BODY = 4_000_000
WEEK_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Daemon:
    """Per-process state: the cached SWODP sessions and the Graph profile."""

    def __init__(self, instance="prod", *, debug=False):
        self.instance = instance
        self.debug = debug
        self.sessions = {}
        self.profile = None
        self.profile_known = False
        # One bridge call at a time: a capture is a headless Edge launch under
        # the sidecar flock, and writes must never interleave.
        self.lock = threading.Lock()

    def with_session(self, instance, function):
        """Run `function(session)`; recapture once when SWODP says it expired."""
        for attempt in (1, 2):
            if instance not in self.sessions:
                self.sessions[instance] = session_mod.capture(instance)
            try:
                return function(self.sessions[instance])
            except AuthExpiredError:
                self.sessions.pop(instance, None)
                if attempt == 2:
                    raise

    def graph_profile(self):
        """Alias of the owa-piggy profile that declares `swodp` (None: broker default)."""
        if not self.profile_known:
            rows = get_profiles(tool_name="owa-swodp")
            aliases = [r.alias for r in rows if session_mod.SERVICE in r.services and r.registered]
            if len(aliases) > 1:
                raise UsageError("several owa-piggy profiles declare swodp; keep it on one (OWA_SERVICES)")
            self.profile = aliases[0] if aliases else None
            self.profile_known = True
        return self.profile


def _instance(message, daemon):
    instance = message.get("instance") or daemon.instance
    session_mod.validate_instance(instance)
    return instance


def _account(access_token):
    """Display name from the (unverified) JWT payload; the token itself is not returned."""
    try:
        segment = access_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
    except (IndexError, ValueError):
        return None
    name = claims.get("preferred_username") or claims.get("upn")
    return name if isinstance(name, str) else None


def calendar_range(today, weeks_back, weeks_forward):
    """Monday-based window, as extension/graph.js fetchCalendarView."""
    monday = today - timedelta(days=today.weekday())
    return monday - timedelta(weeks=weeks_back), monday + timedelta(weeks=weeks_forward, days=6)


def _lower(value):
    return value[:1].lower() + value[1:] if isinstance(value, str) else value


def graph_event(event):
    """Outlook REST event -> the Graph shape the app reads (camelCase, enum values lower-cased)."""
    def moment(value):
        value = value or {}
        return {"dateTime": value.get("DateTime"), "timeZone": value.get("TimeZone")}

    return {
        "subject": event.get("Subject"),
        "start": moment(event.get("Start")),
        "end": moment(event.get("End")),
        "categories": event.get("Categories") or [],
        "showAs": _lower(event.get("ShowAs")),
        "isAllDay": event.get("IsAllDay"),
        "sensitivity": _lower(event.get("Sensitivity")),
        "attendees": [{"type": _lower(a.get("Type"))} for a in event.get("Attendees") or []],
    }


def _weeks(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 12 else 4


def graph_calendar(daemon, message):
    start, end = calendar_range(date.today(), _weeks(message.get("weeksBack")), _weeks(message.get("weeksForward")))
    token = get_token(
        tool_name="owa-swodp", audience="outlook", profile=daemon.graph_profile(), debug=daemon.debug
    )
    url = (
        f"{CALENDAR_VIEW}?startDateTime={start.isoformat()}T00:00:00"
        f"&endDateTime={end.isoformat()}T23:59:59&$select={CALENDAR_SELECT}&$top=100"
    )
    # 30 pages of 100 cover +-12 weeks; more means something is wrong. UTC like Graph's default.
    pages = http.paginate(
        url, token=token.access_token, headers={"Prefer": 'outlook.timezone="UTC"'}, max_pages=30, debug=daemon.debug
    )
    events = [graph_event(event) for event in pages]
    return {
        "exportedAt": datetime.now().astimezone().isoformat(),
        "rangeStart": start.isoformat(),
        "rangeEnd": end.isoformat(),
        "value": events,
        "account": _account(token.access_token),
    }


def _check_rows(rows):
    rows = service.validate_write_rows(rows)
    for row in rows:
        # service.write_week ignores `scope` (the app's month-segment ownership),
        # so a partial scope would PATCH or delete the neighbouring month's card.
        if "scope" in row and sorted(row["scope"] or []) != list(range(7)):
            raise UsageError(
                "rows scoped to a month segment are not supported by owa-swodp serve yet; "
                "write boundary weeks from the extension"
            )
    return rows


def dispatch(daemon, message):
    """One bridge request -> response dict. Errors come back as {error, code}."""
    kind = message.get("type")
    try:
        if kind == "ping":
            return {"ok": True, "version": EXPECTED_BRIDGE_VERSION}
        if kind == "swodp-tab":
            # There is no tab: the sidecar session is captured on demand.
            return {"state": "ready"}
        if kind in ("swodp-open-tab", "graph-signout"):
            return {"ok": True}
        with daemon.lock:
            if kind == "swodp-sync":
                week = message.get("weekStart")
                if not isinstance(week, str) or not WEEK_RE.match(week):
                    return {"error": "weekStart must be YYYY-MM-DD"}
                cards_only = message.get("mode") == "cards"
                instance = _instance(message, daemon)
                result = daemon.with_session(
                    instance,
                    lambda s: service.sync(s, week, cards_only=cards_only, debug=daemon.debug),
                )
                warnings = result.pop("warnings", None)
                return {**result, "warning": " ".join(warnings)} if warnings else result
            if kind == "swodp-write":
                week = message.get("weekStart")
                if not isinstance(week, str) or not WEEK_RE.match(week):
                    return {"error": "weekStart must be YYYY-MM-DD"}
                rows = _check_rows(message.get("rows"))
                instance = _instance(message, daemon)
                return {
                    "results": daemon.with_session(
                        instance, lambda s: service.write_week(s, week, rows, debug=daemon.debug)
                    )
                }
            if kind == "graph-calendar":
                return graph_calendar(daemon, message)
        return {"error": f"unknown message type: {kind}"}
    except AuthExpiredError as exc:
        # The app shows code noSession as "not signed in", not as a failure
        return {"error": redact(exc.message), "code": "noSession"}
    except OwaError as exc:
        return {"error": redact(exc.message), "code": None}


def _origins(port):
    return {f"127.0.0.1:{port}", f"localhost:{port}"}


class Handler(BaseHTTPRequestHandler):
    daemon: Daemon
    app_dir: Path | None
    port: int

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        # Request lines only, and only with --debug: nothing secret is in them
        if self.daemon.debug:
            print(f"DEBUG: {self.command} {self.path.split('?')[0]}", file=sys.stderr)

    def _send(self, status, body=b"", content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, value):
        self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"))

    def _guard(self):
        """DNS-rebinding and cross-origin guard; True when the request may proceed."""
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if host not in _origins(self.port) or (
            origin is not None and origin not in {f"http://{h}" for h in _origins(self.port)}
        ):
            self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden host or origin"})
            return False
        return True

    def do_GET(self):  # noqa: N802
        if not self._guard():
            return
        root = self.app_dir
        if root is None:
            return self._json(HTTPStatus.NOT_FOUND, {"error": "no --app-dir configured"})
        rel = urlsplit(self.path).path.lstrip("/") or "index.html"
        target = (root / rel).resolve()
        if root not in target.parents or not target.is_file():
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, target.read_bytes(), kind)

    def do_POST(self):  # noqa: N802
        if not self._guard():
            return
        if urlsplit(self.path).path != "/bridge":
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Content-Type must be application/json"})
        try:
            length = int(self.headers.get("Content-Length", ""))
            if not 0 < length <= MAX_BODY:
                raise ValueError
            message = json.loads(self.rfile.read(length))
            if not isinstance(message, dict):
                raise ValueError
        except ValueError:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": "body must be a JSON object"})
        self._json(HTTPStatus.OK, dispatch(self.daemon, message))


def make_server(port, daemon, app_dir=None):
    """Bind 127.0.0.1 only. `port` 0 picks a free port (tests)."""
    root = Path(app_dir).expanduser().resolve() if app_dir else None
    if root is not None and not (root / "index.html").is_file():
        raise UsageError(f"--app-dir has no index.html: {root}", remediation="Build the app: npm run build")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    handler = type("BoundHandler", (Handler,), {"daemon": daemon, "app_dir": root, "port": server.server_address[1]})
    server.RequestHandlerClass = handler
    return server
