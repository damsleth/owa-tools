import http.client
import json
import threading
from datetime import date
from types import SimpleNamespace

import pytest

from owa_core.errors import AuthExpiredError, NetworkError, UsageError
from owa_swodp import cli, serve, service

SESSION = SimpleNamespace(instance="prod", host="swodp.example.invalid", user="user@example.invalid")
WEEK_ROWS = [{"taskNumber": "T12345", "days": [8, 0, 0, 0, 0, 0, 0], "description": "work"}]


@pytest.fixture
def daemon(monkeypatch):
    monkeypatch.setattr(serve.session_mod, "capture", lambda instance, **k: SESSION)
    return serve.Daemon("prod")


@pytest.fixture
def running(daemon, tmp_path):
    app = tmp_path / "app"
    (app / "assets").mkdir(parents=True)
    (app / "index.html").write_text("<html>app</html>")
    (app / "assets" / "a.js").write_text("1")
    (tmp_path / "secret.txt").write_text("secret")
    server = serve.make_server(0, daemon, app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def call(port, method, path, body=None, headers=None, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", port)
    merged = {"Host": host or f"127.0.0.1:{port}", **(headers or {})}
    conn.putrequest(method, path, skip_host=True)
    for key, value in merged.items():
        conn.putheader(key, value)
    data = body.encode() if body is not None else None
    conn.putheader("Content-Length", str(len(data or b"")))
    conn.endheaders(data)
    response = conn.getresponse()
    payload = response.read()
    conn.close()
    return response.status, dict(response.getheaders()), payload


def post(port, message, **kw):
    headers = {"Content-Type": "application/json", **kw.pop("headers", {})}
    return call(port, "POST", "/bridge", json.dumps(message), headers, **kw)


def test_ping_and_noops(daemon):
    assert serve.dispatch(daemon, {"type": "ping"}) == {"ok": True, "version": serve.EXPECTED_BRIDGE_VERSION}
    assert serve.dispatch(daemon, {"type": "swodp-tab"}) == {"state": "ready"}
    assert serve.dispatch(daemon, {"type": "swodp-open-tab"}) == {"ok": True}
    assert serve.dispatch(daemon, {"type": "graph-signout"}) == {"ok": True}
    assert "unknown" in serve.dispatch(daemon, {"type": "nope"})["error"]


def test_sync_dispatch_modes_and_warning(daemon, monkeypatch):
    seen = []

    def fake_sync(session, week, *, cards_only, debug):
        seen.append((week, cards_only))
        return {"weekCards": [], "warnings": ["a", "b"]}

    monkeypatch.setattr(service, "sync", fake_sync)
    result = serve.dispatch(daemon, {"type": "swodp-sync", "weekStart": "2026-08-17", "mode": "cards"})
    assert result == {"weekCards": [], "warning": "a b"}
    serve.dispatch(daemon, {"type": "swodp-sync", "weekStart": "2026-08-17"})
    assert seen == [("2026-08-17", True), ("2026-08-17", False)]
    assert "weekStart" in serve.dispatch(daemon, {"type": "swodp-sync", "weekStart": "x"})["error"]


def test_session_cached_and_recaptured_once_on_expiry(daemon, monkeypatch):
    captures = []
    monkeypatch.setattr(serve.session_mod, "capture", lambda i, **k: captures.append(i) or SESSION)
    calls = []

    def flaky(session, week, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise AuthExpiredError("expired")
        return {"weekCards": []}

    monkeypatch.setattr(service, "sync", flaky)
    msg = {"type": "swodp-sync", "weekStart": "2026-08-17"}
    assert serve.dispatch(daemon, msg) == {"weekCards": []}
    assert captures == ["prod", "prod"]
    serve.dispatch(daemon, msg)
    assert captures == ["prod", "prod"]  # cached after the recapture

    def always(*a, **k):
        raise AuthExpiredError("still")

    monkeypatch.setattr(service, "sync", always)
    assert serve.dispatch(daemon, msg)["code"] == "noSession"


def test_errors_carry_code(daemon, monkeypatch):
    def down(*a, **k):
        raise NetworkError("down")

    monkeypatch.setattr(service, "sync", down)
    result = serve.dispatch(daemon, {"type": "swodp-sync", "weekStart": "2026-08-17"})
    assert result == {"error": "down", "code": None}


def test_write_dispatch_and_scope_refusal(daemon, monkeypatch):
    monkeypatch.setattr(
        service, "write_week", lambda s, week, rows, debug: [{"taskNumber": "T12345", "action": "created"}]
    )
    msg = {"type": "swodp-write", "weekStart": "2026-08-17"}
    assert serve.dispatch(daemon, {**msg, "rows": WEEK_ROWS}) == {
        "results": [{"taskNumber": "T12345", "action": "created"}]
    }
    full = [{**WEEK_ROWS[0], "scope": [0, 1, 2, 3, 4, 5, 6]}]
    assert "results" in serve.dispatch(daemon, {**msg, "rows": full})
    partial = [{**WEEK_ROWS[0], "scope": [0, 1, 2]}]
    assert "month segment" in serve.dispatch(daemon, {**msg, "rows": partial})["error"]
    assert "1-200 rows" in serve.dispatch(daemon, {**msg, "rows": []})["error"]


def test_graph_event_reshapes_outlook_rest():
    event = {
        "Subject": "x", "Start": {"DateTime": "2026-10-26T06:00:00.0000000", "TimeZone": "UTC"},
        "End": {"DateTime": "2026-10-26T07:00:00.0000000", "TimeZone": "UTC"}, "Categories": ["SWON"],
        "ShowAs": "WorkingElsewhere", "IsAllDay": False, "Sensitivity": "Private",
        "Attendees": [{"Type": "Resource", "EmailAddress": {}}],
    }
    assert serve.graph_event(event) == {
        "subject": "x", "start": {"dateTime": "2026-10-26T06:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-10-26T07:00:00.0000000", "timeZone": "UTC"}, "categories": ["SWON"],
        "showAs": "workingElsewhere", "isAllDay": False, "sensitivity": "private",
        "attendees": [{"type": "resource"}],
    }
    assert serve.graph_event({})["attendees"] == []


def test_graph_calendar_pages_and_hides_token(daemon, monkeypatch):
    token = SimpleNamespace(access_token="fake.eyJ1cG4iOiJhQGV4YW1wbGUuaW52YWxpZCJ9.sig")
    asked = {}
    monkeypatch.setattr(
        serve,
        "get_profiles",
        lambda **k: [
            SimpleNamespace(alias="p1", services=("owa", "swodp"), registered=True),
            SimpleNamespace(alias="p2", services=("owa",), registered=True),
        ],
    )
    monkeypatch.setattr(serve, "get_token", lambda **k: asked.update(k) or token)
    monkeypatch.setattr(serve.http, "paginate", lambda url, **k: asked.update(url=url) or iter([{"Subject": "x"}]))
    result = serve.dispatch(daemon, {"type": "graph-calendar", "interactive": False})
    assert asked["audience"] == "outlook" and asked["profile"] == "p1"
    assert "$select=Subject,Start,End,Categories,ShowAs,IsAllDay,Sensitivity,Attendees&$top=100" in asked["url"]
    assert set(result) == {"exportedAt", "rangeStart", "rangeEnd", "value", "account"}
    assert result["value"][0]["subject"] == "x" and result["account"] == "a@example.invalid"
    assert "fake" not in json.dumps(result)


def test_graph_profile_ambiguity_and_default(daemon, monkeypatch):
    two = [SimpleNamespace(alias=a, services=("swodp",), registered=True) for a in ("a", "b")]
    monkeypatch.setattr(serve, "get_profiles", lambda **k: two)
    with pytest.raises(UsageError):
        daemon.graph_profile()
    monkeypatch.setattr(serve, "get_profiles", lambda **k: [])
    assert serve.Daemon().graph_profile() is None


def test_calendar_range_matches_extension():
    # Wednesday 2026-10-28 -> Monday 2026-10-26; +-4 weeks, end = last Sunday
    assert serve.calendar_range(date(2026, 10, 28), 4, 4) == (date(2026, 9, 28), date(2026, 11, 29))
    assert serve.calendar_range(date(2026, 11, 1), 0, 0) == (date(2026, 10, 26), date(2026, 11, 1))


def test_http_bridge_roundtrip_and_no_cors(running):
    status, headers, body = post(running, {"type": "ping"})
    assert status == 200 and json.loads(body)["ok"] is True
    assert not [h for h in headers if h.lower().startswith("access-control")]
    assert post(running, {"type": "ping"}, host=f"localhost:{running}")[0] == 200


@pytest.mark.parametrize("host", ["evil.example:8765", "127.0.0.1:1", "127.0.0.1", "rebind.example"])
def test_bad_host_rejected(running, host):
    assert post(running, {"type": "ping"}, host=host)[0] == 403
    assert call(running, "GET", "/", host=host)[0] == 403


def test_foreign_origin_rejected_own_origin_allowed(running):
    assert post(running, {"type": "ping"}, headers={"Origin": "http://localhost:5173"})[0] == 403
    assert post(running, {"type": "ping"}, headers={"Origin": "null"})[0] == 403
    assert post(running, {"type": "ping"}, headers={"Origin": f"http://127.0.0.1:{running}"})[0] == 200


def test_content_type_and_body_validation(running):
    for ctype in ("text/plain", "application/x-www-form-urlencoded", ""):
        headers = {"Content-Type": ctype} if ctype else {}
        assert call(running, "POST", "/bridge", '{"type":"ping"}', headers)[0] == 415
    json_type = {"Content-Type": "application/json"}
    assert call(running, "POST", "/bridge", "[1]", json_type)[0] == 400
    assert call(running, "POST", "/bridge", "nope", {"Content-Type": "application/json; charset=utf-8"})[0] == 400
    assert call(running, "POST", "/other", "{}", json_type)[0] == 404


def test_static_files_and_traversal(running):
    status, headers, body = call(running, "GET", "/")
    assert status == 200 and body == b"<html>app</html>" and headers["Content-Type"].startswith("text/html")
    assert call(running, "GET", "/assets/a.js")[0] == 200
    assert call(running, "GET", "/assets")[0] == 404
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        assert call(running, "GET", path)[0] == 404


def test_no_app_dir_and_missing_index(daemon, tmp_path):
    server = serve.make_server(0, daemon)
    assert server.server_address[0] == "127.0.0.1"
    server.server_close()
    with pytest.raises(UsageError, match="index.html"):
        serve.make_server(0, daemon, tmp_path)


def test_cli_registers_serve_and_validates_port(capsys):
    assert "serve" in {row["name"] for row in cli.COMMAND_SCHEMA}
    assert cli.main(["serve", "--port", "99999"]) != 0
    assert "--port" in capsys.readouterr().err
