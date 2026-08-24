from types import SimpleNamespace

import pytest

from owa_core.errors import AuthExpiredError, UsageError
from owa_swodp import session


class FakeProcess:
    def __init__(self):
        self.terminated = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout):
        return 0


class FakeCdp:
    def __init__(self, port, url):
        self.closed = False

    def call(self, method, params=None, **kwargs):
        if method == "Runtime.evaluate":
            return {"result": {"value": {"user": "user@example.invalid", "token": "fake-gck"}}}
        if method == "Network.getCookies":
            return {"cookies": [{"name": "fake", "value": "cookie"}]}
        return {}

    def close(self):
        self.closed = True


def test_profile_dirs_are_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("OWA_SWODP_CONFIG_DIR", str(tmp_path))
    assert session.profile_dir("prod") == tmp_path / "edge-profile"
    assert session.profile_dir("uat") == tmp_path / "edge-profile-uat"
    with pytest.raises(UsageError):
        session.profile_dir("dev")


def test_capture_returns_in_memory_credentials_and_terminates(tmp_path, monkeypatch):
    process = FakeProcess()
    monkeypatch.setenv("OWA_SWODP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(session, "find_free_port", lambda: 1234)
    monkeypatch.setattr(session, "launch_edge", lambda *a, **k: process)
    monkeypatch.setattr(
        session, "find_tab", lambda *a, **k: {"webSocketDebuggerUrl": "ws://localhost/devtools/page/1"}
    )
    monkeypatch.setattr(session, "CdpSession", FakeCdp)
    captured = session.capture("prod")
    assert captured.user == "user@example.invalid"
    assert captured.cookie_header == "fake=cookie"
    assert process.terminated is True
    assert tmp_path.stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "edge-profile").stat().st_mode & 0o777 == 0o700


def test_capture_times_out_without_identity(tmp_path, monkeypatch):
    class GuestCdp(FakeCdp):
        def call(self, method, params=None, **kwargs):
            if method == "Runtime.evaluate":
                return {"result": {"value": {"user": "guest", "token": None}}}
            return super().call(method, params, **kwargs)

    monkeypatch.setenv("OWA_SWODP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(session, "find_free_port", lambda: 1234)
    monkeypatch.setattr(session, "launch_edge", lambda *a, **k: FakeProcess())
    monkeypatch.setattr(
        session, "find_tab", lambda *a, **k: {"webSocketDebuggerUrl": "ws://localhost/devtools/page/1"}
    )
    monkeypatch.setattr(session, "CdpSession", GuestCdp)
    with pytest.raises(AuthExpiredError, match="not authenticated"):
        session.capture("prod", timeout=0)


def test_find_edge_and_launch_arguments(tmp_path, monkeypatch):
    monkeypatch.setattr(session.os.path, "isfile", lambda path: path == session._EDGE_CANDIDATES[0])
    monkeypatch.setattr(session.os, "access", lambda *a: True)
    assert session.find_edge() == session._EDGE_CANDIDATES[0]

    seen = {}
    monkeypatch.setattr(
        session.subprocess,
        "Popen",
        lambda args, **kwargs: seen.update(args=args, kwargs=kwargs) or SimpleNamespace(),
    )
    session.launch_edge(tmp_path, 9222, headless=True, url="https://example.invalid")
    assert "--headless=new" in seen["args"]
    assert "--remote-debugging-address=127.0.0.1" in seen["args"]


def test_launch_visible_and_missing_edge(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "find_edge", lambda: None)
    with pytest.raises(UsageError, match="not found"):
        session.launch_edge(tmp_path, 1, headless=False, url="https://example.invalid")
    monkeypatch.setattr(session, "find_edge", lambda: "/fake/edge")
    seen = {}
    monkeypatch.setattr(
        session.subprocess,
        "Popen",
        lambda args, **kwargs: seen.update(args=args) or SimpleNamespace(),
    )
    session.launch_edge(tmp_path, 1, headless=False, url="https://example.invalid")
    assert "--window-position=100,100" in seen["args"]


def test_terminate_kills_after_timeout():
    class SlowProcess(FakeProcess):
        def wait(self, timeout):
            raise session.subprocess.TimeoutExpired("edge", timeout)

        def kill(self):
            self.killed = True

    process = SlowProcess()
    session._terminate(process)
    assert process.killed is True


def test_capture_rejects_empty_cookies(tmp_path, monkeypatch):
    class NoCookies(FakeCdp):
        def call(self, method, params=None, **kwargs):
            if method == "Network.getCookies":
                return {"cookies": []}
            return super().call(method, params, **kwargs)

    monkeypatch.setenv("OWA_SWODP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(session, "find_free_port", lambda: 1234)
    monkeypatch.setattr(session, "launch_edge", lambda *a, **k: FakeProcess())
    monkeypatch.setattr(
        session, "find_tab", lambda *a, **k: {"webSocketDebuggerUrl": "ws://localhost/devtools/page/1"}
    )
    monkeypatch.setattr(session, "CdpSession", NoCookies)
    with pytest.raises(AuthExpiredError, match="no session cookies"):
        session.capture("prod")
