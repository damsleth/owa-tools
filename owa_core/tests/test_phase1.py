"""Phase 1 unit tests for owa_core. These replace the Phase 0 stub
tests once the modules are implemented."""
from __future__ import annotations

import base64
import io
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from owa_core import (
    auth, config, dates, dispatch, errors, format, http, jwt, tty,
)


# ---------- errors ----------

def test_errors_taxonomy_present():
    assert errors.ExitCode.OK == 0
    assert errors.ExitCode.USAGE == 2
    assert errors.ExitCode.AUTH_EXPIRED == 11
    assert errors.ExitCode.RATE_LIMITED == 14


def test_error_classes_have_codes():
    pairs = [
        (errors.UsageError, errors.ExitCode.USAGE),
        (errors.NetworkError, errors.ExitCode.NETWORK),
        (errors.AuthExpiredError, errors.ExitCode.AUTH_EXPIRED),
        (errors.ScopeInsufficientError, errors.ExitCode.SCOPE_INSUFFICIENT),
        (errors.NotFoundError, errors.ExitCode.NOT_FOUND),
        (errors.RateLimitedError, errors.ExitCode.RATE_LIMITED),
        (errors.ConflictError, errors.ExitCode.CONFLICT),
        (errors.InternalError, errors.ExitCode.INTERNAL),
    ]
    for cls, code in pairs:
        assert cls.code == code


def test_emit_human():
    buf = io.StringIO()
    err = errors.UsageError("missing flag", hint="try --help")
    code = errors.emit(err, tool="owa-cal", command="events", stream=buf)
    text = buf.getvalue()
    assert code == int(errors.ExitCode.USAGE)
    assert "ERROR: missing flag" in text
    assert "hint: try --help" in text


def test_emit_json():
    buf = io.StringIO()
    err = errors.AuthExpiredError("expired", hint="reseed")
    code = errors.emit(err, tool="owa-cal", command="events",
                       err_json=True, stream=buf)
    obj = json.loads(buf.getvalue())
    assert code == 11
    assert obj["error"]["code"] == "AUTH_EXPIRED"
    assert obj["error"]["exit_code"] == 11
    assert obj["error"]["tool"] == "owa-cal"
    assert obj["error"]["command"] == "events"
    assert obj["error"]["hint"] == "reseed"


# ---------- jwt ----------

def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.signature"


def test_jwt_decode_padding_and_claims():
    tok = _make_jwt({"exp": 1700000000, "scp": "Mail.Read Calendars.ReadWrite"})
    decoded = jwt.decode(tok)
    assert decoded["payload"]["exp"] == 1700000000
    assert jwt.expires_at(tok) == 1700000000
    assert jwt.scopes(tok) == ["Mail.Read", "Calendars.ReadWrite"]


def test_jwt_invalid():
    with pytest.raises(errors.UsageError):
        jwt.decode("notajwt")
    with pytest.raises(errors.UsageError):
        jwt.expires_at(_make_jwt({}))


def test_jwt_missing_scopes_returns_empty():
    assert jwt.scopes(_make_jwt({"exp": 1})) == []


# ---------- tty ----------

def test_is_interactive_off_when_pipe(monkeypatch):
    class Fake:
        def isatty(self):
            return False
    monkeypatch.setattr("sys.stdin", Fake())
    monkeypatch.setattr("sys.stderr", Fake())
    assert tty.is_interactive() is False


def test_confirm_refuses_off_tty(monkeypatch):
    class Fake:
        def isatty(self):
            return False
    monkeypatch.setattr("sys.stdin", Fake())
    monkeypatch.setattr("sys.stderr", Fake())
    with pytest.raises(errors.UsageError):
        tty.confirm("really?")


def test_confirm_force_returns_true():
    assert tty.confirm("really?", force=True) is True


# ---------- config ----------

def test_config_atomic_roundtrip(tmp_path):
    cfg_path = tmp_path / "config"
    c = config.Config(cfg_path, allowed_keys=("profile", "audience"))
    c.set("profile", "work")
    c.set("audience", "outlook")
    c.save_atomic()
    assert cfg_path.read_text(encoding="utf-8") == "audience=outlook\nprofile=work\n"
    mode = os.stat(cfg_path).st_mode & 0o777
    assert mode == 0o600


def test_config_allowlist_rejects_unknown(tmp_path):
    c = config.Config(tmp_path / "c", allowed_keys=("profile",))
    with pytest.raises(errors.UsageError):
        c.set("nope", "x")
    with pytest.raises(errors.UsageError):
        c.get("nope")


def test_config_load_skips_unknown_keys(tmp_path):
    p = tmp_path / "c"
    p.write_text("profile=work\nstray=ignored\n# comment\n", encoding="utf-8")
    c = config.Config(p, allowed_keys=("profile",))
    assert c.get("profile") == "work"


# ---------- dates ----------

def test_dates_parse_iso_with_z():
    dt = dates.parse("2026-05-05T10:00:00Z")
    assert dt.tzinfo is not None
    assert dt == datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)


def test_dates_parse_naive_adopts_default_tz():
    dt = dates.parse("2026-05-05T10:00:00", default_tz=timezone(timedelta(hours=2)))
    assert dt.utcoffset() == timedelta(hours=2)


def test_dates_iso_week_bounds():
    monday, sunday = dates.iso_week(2026, 1)
    assert monday.weekday() == 0
    assert (sunday - monday) == timedelta(days=6)


def test_dates_resolve_tz_windows_alias():
    tz = dates.resolve_tz("W. Europe Standard Time")
    name = getattr(tz, "key", None) or str(tz)
    assert "Europe" in name or "UTC" in name  # zoneinfo may be missing


def test_dates_resolve_tz_none_is_utc():
    assert dates.resolve_tz(None) == timezone.utc


# ---------- format ----------

def test_format_render_json():
    assert format.render({"a": 1}) == '{"a": 1}'


def test_format_pretty_table():
    text = format.pretty_table([{"a": 1, "b": "x"}, {"a": 22, "b": "yz"}])
    lines = text.splitlines()
    assert lines[0].startswith("a ")
    assert "22" in lines[-1]


def test_format_csv():
    text = format.to_csv([{"a": "hi", "b": "x,y"}], columns=("a", "b"))
    assert text.splitlines() == ["a,b", "hi,\"x,y\""]


def test_format_ndjson():
    text = format.to_ndjson([{"a": 1}, {"a": 2}])
    assert text == '{"a": 1}\n{"a": 2}\n'


def test_format_render_unknown():
    with pytest.raises(errors.UsageError):
        format.render({}, format="xml")


# ---------- http ----------

class _FakeResp:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self._body = body
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_http_request_success(monkeypatch):
    captured = {}
    def fake_urlopen(req, *a, **kw):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        return _FakeResp(200, {"Content-Type": "application/json"}, b'{"ok": true}')
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    r = http.request("GET", "https://x/y", token="t", retry=1,
                     _sleep=lambda s: None)
    assert r.status == 200
    assert r.json == {"ok": True}
    assert captured["headers"]["Authorization"] == "Bearer t"


def test_http_request_401_raises_auth_expired(monkeypatch):
    def fake_urlopen(req, *a, **kw):
        import urllib.error
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized",
                                     {"Content-Type": "application/json"},
                                     io.BytesIO(b'{"error":"expired"}'))
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(errors.AuthExpiredError):
        http.request("GET", "https://x", token="t", retry=1,
                     _sleep=lambda s: None)


def test_http_request_429_then_success(monkeypatch):
    calls = {"n": 0}
    def fake_urlopen(req, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            import urllib.error
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests",
                                         {"Retry-After": "0"}, io.BytesIO(b""))
        return _FakeResp(200, {"Content-Type": "application/json"}, b'{"ok":1}')
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    r = http.request("GET", "https://x", token="t", retry=2,
                     _sleep=lambda s: None)
    assert r.status == 200
    assert calls["n"] == 2


def test_http_request_500_exhausted(monkeypatch):
    def fake_urlopen(req, *a, **kw):
        import urllib.error
        raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, io.BytesIO(b""))
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(errors.NetworkError):
        http.request("GET", "https://x", token="t", retry=2,
                     _sleep=lambda s: None)


# ---------- auth ----------

def test_require_min_piggy_too_old(monkeypatch):
    class P:
        returncode = 0
        stdout = "owa-piggy 0.1.0\n"
        stderr = ""
    monkeypatch.setattr(auth.shutil, "which", lambda x: "/fake/owa-piggy")
    monkeypatch.setattr(auth.subprocess, "run", lambda *a, **kw: P())
    with pytest.raises(errors.UsageError):
        auth.require_min_piggy("0.6.0")


def test_require_min_piggy_ok(monkeypatch):
    class P:
        returncode = 0
        stdout = "owa-piggy 0.7.1\n"
        stderr = ""
    monkeypatch.setattr(auth.shutil, "which", lambda x: "/fake/owa-piggy")
    monkeypatch.setattr(auth.subprocess, "run", lambda *a, **kw: P())
    auth.require_min_piggy("0.6.0")  # no raise


def test_get_token_subprocess_failure(monkeypatch):
    class P:
        returncode = 1
        stdout = ""
        stderr = "refresh failed: invalid_grant"
    monkeypatch.setattr(auth.shutil, "which", lambda x: "/fake/owa-piggy")
    monkeypatch.setattr(auth.subprocess, "run", lambda *a, **kw: P())
    with pytest.raises(errors.AuthExpiredError):
        auth.get_token("work", "outlook")


def test_get_token_success(monkeypatch):
    payload = {"exp": int(time.time()) + 3600,
               "scp": "Mail.Read",
               "aud": "https://outlook.office.com",
               "upn": "u@x"}
    fake_token = _make_jwt(payload)
    class P:
        returncode = 0
        stdout = json.dumps({"access_token": fake_token})
        stderr = ""
    monkeypatch.setattr(auth.shutil, "which", lambda x: "/fake/owa-piggy")
    monkeypatch.setattr(auth.subprocess, "run", lambda *a, **kw: P())
    tok = auth.get_token(None, "outlook")
    assert tok.access_token == fake_token
    assert "Mail.Read" in tok.scopes
    ident = auth.verify_identity(tok, "outlook")
    assert ident["upn"] == "u@x"


# ---------- dispatch ----------

def _toy_spec():
    def hello(args, flags, spec):
        return {"greeting": f"hi {args.get('name') or 'world'}"}
    def boom(args, flags, spec):
        raise errors.NotFoundError("nope")
    return dispatch.Spec(
        tool="owa-toy",
        version="9.9.9",
        commands=(
            dispatch.Command(
                name="hello",
                summary="say hi",
                args=(dispatch.Arg("name"),),
                flags=(dispatch.Flag("--shout", type=bool, default=False),),
                handler=hello,
                schema_version=1,
            ),
            dispatch.Command(name="boom", handler=boom),
        ),
    )


def test_dispatch_help_no_args():
    spec = _toy_spec()
    out = io.StringIO(); err = io.StringIO()
    code = dispatch.run(spec, [], stdout=out, stderr=err)
    assert code == 0
    assert "owa-toy" in out.getvalue()
    assert "hello" in out.getvalue()


def test_dispatch_help_json():
    spec = _toy_spec()
    out = io.StringIO(); err = io.StringIO()
    dispatch.run(spec, ["--help", "--json"], stdout=out, stderr=err)
    obj = json.loads(out.getvalue())
    assert obj["tool"] == "owa-toy"
    assert obj["commands"][0]["name"] == "hello"


def test_dispatch_schema_command():
    spec = _toy_spec()
    out = io.StringIO(); err = io.StringIO()
    dispatch.run(spec, ["schema", "hello"], stdout=out, stderr=err)
    obj = json.loads(out.getvalue())
    assert obj["name"] == "hello"
    assert obj["args"][0]["name"] == "name"


def test_dispatch_runs_handler_legacy_shape():
    spec = _toy_spec()
    out = io.StringIO(); err = io.StringIO()
    code = dispatch.run(spec, ["hello", "Kim"], stdout=out, stderr=err)
    assert code == 0
    obj = json.loads(out.getvalue())
    assert obj == {"greeting": "hi Kim"}  # no envelope without --agent


def test_dispatch_agent_envelope():
    spec = _toy_spec()
    out = io.StringIO(); err = io.StringIO()
    code = dispatch.run(spec, ["hello", "Kim", "--agent"], stdout=out, stderr=err)
    obj = json.loads(out.getvalue())
    assert obj["_owa"]["tool"] == "owa-toy"
    assert obj["_owa"]["schema"] == 1
    assert obj["data"] == {"greeting": "hi Kim"}


def test_dispatch_unknown_flag():
    spec = _toy_spec()
    out = io.StringIO(); err = io.StringIO()
    code = dispatch.run(spec, ["hello", "Kim", "--what"], stdout=out, stderr=err)
    assert code == 2
    assert "unknown flag" in err.getvalue()


def test_dispatch_owa_error_maps_exit_code():
    spec = _toy_spec()
    out = io.StringIO(); err = io.StringIO()
    code = dispatch.run(spec, ["boom"], stdout=out, stderr=err)
    assert code == 13
    assert "ERROR" in err.getvalue()


def test_dispatch_err_json():
    spec = _toy_spec()
    out = io.StringIO(); err = io.StringIO()
    code = dispatch.run(spec, ["boom", "--err-json"], stdout=out, stderr=err)
    assert code == 13
    obj = json.loads(err.getvalue())
    assert obj["error"]["code"] == "NOT_FOUND"
