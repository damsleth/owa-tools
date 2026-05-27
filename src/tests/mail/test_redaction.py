"""Redaction regression: a message body must never reach stderr on
owa-mail send / reply / forward failure paths - not even with --debug,
which prints request bodies and error responses (the worst case for a
body leak).

The redaction lives in owa_core.http: the debug request-body print
runs json.dumps(body) through redact(), and error responses are
redacted before they're formatted into the raised error. These tests
drive the *real* http layer with a fake transport so those redact()
calls actually execute - a regression in redaction fails here, not a
stubbed-out copy.

The message text carries a sentinel; we assert (a) the command failed
on the body-bearing call, (b) the sentinel really was transmitted in a
request body (so the test isn't vacuous), and (c) it never appears on
stderr or stdout.
"""
import urllib.error

import pytest

from owa_mail import cli

SENTINEL = 'CANARY_SECRET_xxxx'


class _FakeResp:
    """Minimal stand-in for an http.client response used as a context
    manager by owa_core.http.request."""

    def __init__(self, body=b'{"id":"draft-1"}'):
        self._body = body
        self.status = 200
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


class _FakeHTTPError(urllib.error.HTTPError):
    """A 400 whose response body is generic - servers do not echo the
    message content, so the leak we guard against is the *request* body,
    redacted by the debug print."""

    def __init__(self, body):
        super().__init__('https://outlook.test/x', 400, 'Bad Request', {}, None)
        self._body = body.encode('utf-8')

    def read(self):
        return self._body


@pytest.fixture(autouse=True)
def _force_debug(monkeypatch):
    # --debug / MAIL_DEBUG is the noisiest path: it prints request
    # bodies and error responses. Exercise the worst case.
    monkeypatch.setenv('MAIL_DEBUG', '1')


def _install_transport(monkeypatch):
    """Drive the real owa_core.http.request, but inject a fake urlopen
    that fails the call carrying the message body (the request whose
    data contains the sentinel) and succeeds on the orchestration calls
    before it. Returns the list of raw request bodies the transport saw."""
    seen_bodies = []
    real_request = cli.api_mod.http.request

    def _fake_urlopen(req, timeout=None):
        data = req.data or b''
        text = data.decode('utf-8', errors='replace') if isinstance(data, (bytes, bytearray)) else str(data)
        seen_bodies.append(text)
        if SENTINEL in text:
            raise _FakeHTTPError('{"error":{"code":"ErrorInvalidRecipients","message":"bad request"}}')
        return _FakeResp()

    def _wrapped(*args, **kwargs):
        kwargs.setdefault('urlopen', _fake_urlopen)
        return real_request(*args, **kwargs)

    monkeypatch.setattr(cli.api_mod.http, 'request', _wrapped)
    return seen_bodies


def _assert_no_leak(rc, capsys, seen_bodies):
    captured = capsys.readouterr()
    # The command failed on the body-bearing call.
    assert rc != 0
    # Non-vacuous: the sentinel really was transmitted in a request body.
    assert any(SENTINEL in b for b in seen_bodies)
    # ...but redaction kept it off both streams.
    assert SENTINEL not in captured.err
    assert SENTINEL not in captured.out


def test_send_failure_does_not_leak_body(monkeypatch, capsys):
    seen = _install_transport(monkeypatch)
    rc = cli.cmd_send(
        ['--to', 'a@example.com', '--subject', 'hi', '--body', f'secret {SENTINEL} here'],
        {}, 'tok', 'https://outlook.test',
    )
    _assert_no_leak(rc, capsys, seen)


def test_reply_failure_does_not_leak_body(monkeypatch, capsys):
    seen = _install_transport(monkeypatch)
    rc = cli.cmd_reply(
        ['--id', 'm1', '--body', f'reply {SENTINEL} text'],
        {}, 'tok', 'https://outlook.test',
    )
    _assert_no_leak(rc, capsys, seen)


def test_forward_failure_does_not_leak_body(monkeypatch, capsys):
    seen = _install_transport(monkeypatch)
    rc = cli.cmd_forward(
        ['--id', 'm1', '--to', 'c@example.com', '--body', f'fwd {SENTINEL} note'],
        {}, 'tok', 'https://outlook.test',
    )
    _assert_no_leak(rc, capsys, seen)
