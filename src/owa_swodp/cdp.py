"""Minimal stdlib Chrome DevTools Protocol client.

session.py uses it to drive Edge: find the page tab, open its WebSocket and
issue request/response ``call``s (Runtime.evaluate, Network.getCookies).
Ported from owa-piggy's cdp.py; the framing (length encodings, masking,
ping/pong) is regression-tested in tests/swodp/test_cdp.py.
"""
import base64
import json
import secrets
import socket
import struct
import time
import urllib.request


def find_tab(port, timeout=15.0):
    """Poll http://localhost:<port>/json until at least one page-type
    target appears, then return that target's metadata dict.

    Edge needs a moment after launch before its CDP HTTP endpoint is
    ready; we retry every 200ms. Any non-page targets (service workers,
    extension backgrounds) are ignored - we want the user-facing tab.
    """
    deadline = time.monotonic() + timeout
    last_err = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f'http://localhost:{port}/json',
                                        timeout=2) as r:
                tabs = json.loads(r.read())
            pages = [t for t in tabs if t.get('type') == 'page']
            if pages:
                return pages[0]
            last_err = f'no page targets yet (saw {len(tabs)} total)'
        except Exception as e:
            last_err = str(e)
        time.sleep(0.2)
    raise TimeoutError(f'CDP tab not ready on port {port}: {last_err}')


def _ws_handshake(host, port, path):
    """Open a raw WebSocket to ws://host:port<path>. Returns the socket
    after the 101 Switching Protocols response is consumed."""
    key = base64.b64encode(secrets.token_bytes(16)).decode()
    s = socket.create_connection((host, port))
    req = (
        f'GET {path} HTTP/1.1\r\n'
        f'Host: {host}:{port}\r\n'
        'Upgrade: websocket\r\n'
        'Connection: Upgrade\r\n'
        f'Sec-WebSocket-Key: {key}\r\n'
        'Sec-WebSocket-Version: 13\r\n'
        '\r\n'
    )
    s.sendall(req.encode())
    buf = b''
    while b'\r\n\r\n' not in buf:
        chunk = s.recv(4096)
        if not chunk:
            raise ConnectionError('WS handshake: connection closed')
        buf += chunk
    status = buf.split(b'\r\n', 1)[0]
    if b' 101 ' not in status:
        raise ConnectionError(f'WS handshake failed: {status!r}')
    return s


def _send_frame(s, opcode, payload):
    """Send one masked frame (client -> server, RFC 6455)."""
    data = payload.encode('utf-8') if isinstance(payload, str) else payload
    mask = secrets.token_bytes(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    L = len(data)
    hdr = bytes([0x80 | (opcode & 0x0f)])
    if L < 126:
        hdr += bytes([0x80 | L])
    elif L < 65536:
        hdr += bytes([0x80 | 126]) + struct.pack('>H', L)
    else:
        hdr += bytes([0x80 | 127]) + struct.pack('>Q', L)
    s.sendall(hdr + mask + masked)


def _recv_exact(s, n):
    buf = b''
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise ConnectionError('WS: connection closed mid-frame')
        buf += chunk
    return buf


def _recv_frame(s):
    """Receive one frame, handling fragmentation and control frames.
    Returns the full text payload as a str, or raises if the server
    closes the connection. Pings are answered inline with a pong."""
    parts = []
    while True:
        b1, b2 = _recv_exact(s, 2)
        fin = b1 & 0x80
        opcode = b1 & 0x0f
        masked = b2 & 0x80
        L = b2 & 0x7f
        if L == 126:
            L = struct.unpack('>H', _recv_exact(s, 2))[0]
        elif L == 127:
            L = struct.unpack('>Q', _recv_exact(s, 8))[0]
        if masked:
            mask = _recv_exact(s, 4)
            payload = bytes(b ^ mask[i % 4]
                            for i, b in enumerate(_recv_exact(s, L)))
        else:
            payload = _recv_exact(s, L)
        if opcode == 0x9:  # ping -> pong
            _send_frame(s, 0xA, payload)
            continue
        if opcode == 0x8:  # close
            raise ConnectionError('WS: server sent close')
        parts.append(payload)
        if fin:
            break
    return b''.join(parts).decode('utf-8')


class CdpSession:
    """One WebSocket to a CDP target, used for request/response calls.

    Server-pushed events (messages without our `id`) are ignored.
    """

    def __init__(self, port, ws_url):
        path = '/' + ws_url.split('/', 3)[3]
        self._sock = _ws_handshake('localhost', port, path)
        self._next_id = 0

    def call(self, method, params=None, *, timeout=30.0):
        """Send a CDP command, return its `result` dict.

        Raises TimeoutError if no matching reply arrives within `timeout`."""
        self._next_id += 1
        msg_id = self._next_id
        _send_frame(self._sock, 0x1, json.dumps({
            'id': msg_id,
            'method': method,
            'params': params or {},
        }))
        self._sock.settimeout(timeout)
        try:
            while True:
                msg = json.loads(_recv_frame(self._sock))
                if msg.get('id') == msg_id:
                    if 'error' in msg:
                        raise CdpError(method, msg['error'])
                    return msg.get('result', {})
        finally:
            self._sock.settimeout(None)

    def close(self):
        try:
            self._sock.close()
        except Exception:
            pass


class CdpError(RuntimeError):
    """Raised when a CDP method returns an error envelope."""
    def __init__(self, method, error):
        super().__init__(f'CDP {method} failed: {error}')
        self.method = method
        self.error = error
