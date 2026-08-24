import json
import socket
import threading

import pytest

from owa_swodp import cdp


def _roundtrip(payload, opcode=0x1):
    left, right = socket.socketpair()
    try:
        thread = threading.Thread(target=cdp._send_frame, args=(left, opcode, payload))
        thread.start()
        result = cdp._recv_frame(right)
        thread.join(5)
        return result
    finally:
        left.close()
        right.close()


@pytest.mark.parametrize("size", [0, 5, 125, 126, 65535, 65536])
def test_frame_roundtrip_lengths(size):
    assert _roundtrip("x" * size) == "x" * size


def test_frame_unicode_and_close():
    assert _roundtrip("héllo — ✓") == "héllo — ✓"
    left, right = socket.socketpair()
    try:
        threading.Thread(target=cdp._send_frame, args=(left, 0x8, b"")).start()
        with pytest.raises(ConnectionError):
            cdp._recv_frame(right)
    finally:
        left.close()
        right.close()


def test_ping_is_answered_before_text():
    left, right = socket.socketpair()
    try:
        def sender():
            cdp._send_frame(left, 0x9, b"ping")
            cdp._send_frame(left, 0x1, "text")

        thread = threading.Thread(target=sender)
        thread.start()
        assert cdp._recv_frame(right) == "text"
        thread.join(5)
        assert cdp._recv_frame(left) == "ping"
    finally:
        left.close()
        right.close()


class FakeSocket:
    def __init__(self, chunks=None):
        self.chunks = list(chunks or [])
        self.sent = b""
        self.closed = False
        self.timeouts = []

    def recv(self, size):
        return self.chunks.pop(0) if self.chunks else b""

    def sendall(self, data):
        self.sent += data

    def settimeout(self, value):
        self.timeouts.append(value)

    def close(self):
        self.closed = True


def test_find_tab_retries_then_returns_page(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps([{"type": "page", "id": "one"}]).encode()

    monkeypatch.setattr(cdp.urllib.request, "urlopen", lambda *a, **k: Response())
    assert cdp.find_tab(9222)["id"] == "one"


def test_ws_handshake_and_exact_read_failures(monkeypatch):
    sock = FakeSocket([b"HTTP/1.1 101 Switching Protocols\r\n\r\n"])
    monkeypatch.setattr(cdp.socket, "create_connection", lambda *a: sock)
    assert cdp._ws_handshake("localhost", 1, "/devtools") is sock
    assert b"Upgrade: websocket" in sock.sent
    with pytest.raises(ConnectionError, match="mid-frame"):
        cdp._recv_exact(FakeSocket(), 1)


def test_cdp_session_call_buffers_events_and_maps_error(monkeypatch):
    sock = FakeSocket()
    messages = iter(
        [
            json.dumps({"method": "Network.event", "params": {"x": 1}}),
            json.dumps({"id": 1, "result": {"ok": True}}),
            json.dumps({"id": 2, "error": {"message": "bad"}}),
        ]
    )
    monkeypatch.setattr(cdp, "_ws_handshake", lambda *a: sock)
    monkeypatch.setattr(cdp, "_recv_frame", lambda *a: next(messages))
    monkeypatch.setattr(cdp, "_send_frame", lambda *a: None)
    session = cdp.CdpSession(1, "ws://localhost/devtools/page/1")
    assert session.call("Runtime.enable") == {"ok": True}
    assert session.wait_event("Network.event") == {"x": 1}
    with pytest.raises(cdp.CdpError, match="bad"):
        session.call("Bad.method")
    session.close()
    assert sock.closed


def test_wait_event_reads_until_predicate_matches(monkeypatch):
    sock = FakeSocket()
    messages = iter(
        [
            json.dumps({"id": 99, "result": {}}),
            json.dumps({"method": "Event", "params": {"value": 1}}),
            json.dumps({"method": "Event", "params": {"value": 2}}),
        ]
    )
    monkeypatch.setattr(cdp, "_ws_handshake", lambda *a: sock)
    monkeypatch.setattr(cdp, "_recv_frame", lambda *a: next(messages))
    session = cdp.CdpSession(1, "ws://localhost/devtools/page/1")
    assert session.wait_event("Event", lambda value: value["value"] == 2) == {"value": 2}
    assert session.wait_event("Event") == {"value": 1}
