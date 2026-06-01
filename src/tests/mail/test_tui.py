"""Tests for the owa-mail TUI.

The curses event loop is not unit-tested (it needs a terminal); we cover
the pure layout helpers, the thin network wrappers, and the guard that
refuses to launch without an interactive terminal.
"""
import pytest

from owa_mail import cli, tui


def _raw(msg_id, received, subject, **over):
    raw = {
        "Id": msg_id,
        "ReceivedDateTime": received,
        "Subject": subject,
        "From": {"EmailAddress": {"Address": "ada@example.com"}},
        "BodyPreview": "preview text",
        "IsRead": False,
        "HasAttachments": False,
        "Flag": {"FlagStatus": "NotFlagged"},
    }
    raw.update(over)
    return raw


# --- pure layout helpers ---------------------------------------------------

def test_list_row_fits_width_and_shows_fields():
    msg = {
        "received": "2026-05-11T09:30:00Z",
        "from": "ada@example.com",
        "subject": "Hello there",
        "is_read": False,
    }
    row = tui.list_row(msg, 80)
    assert len(row) <= 80
    assert "2026-05-11" in row
    assert "09:30" in row
    assert "ada@example.com" in row
    assert "Hello there" in row
    # marker column = len("2026-05-11") + 1 + len("09:30") + 1 = 17
    assert row[17] == "*"


def test_list_row_read_message_has_no_unread_marker():
    msg = {"received": "2026-05-11T09:30:00Z", "from": "a@b.c",
           "subject": "x", "is_read": True}
    assert tui.list_row(msg, 80)[17] == " "


def test_list_row_truncates_to_narrow_width():
    msg = {"received": "2026-05-11T09:30:00Z", "from": "a@b.c",
           "subject": "x" * 200, "is_read": True}
    assert len(tui.list_row(msg, 30)) <= 30


def test_reader_lines_wrap_and_include_footnote_links():
    msg = {
        "from": "ada@example.com",
        "subject": "Login",
        "received": "2026-05-11T09:30:00Z",
        "body_type": "html",
        "body": "<p>Click <a href='https://x.test/login'>here</a></p>",
    }
    lines = tui.reader_lines(msg, 40)
    assert all(len(ln) <= 40 for ln in lines)
    joined = "\n".join(lines)
    assert "Subject: Login" in joined
    assert "here [1]" in joined
    assert "https://x.test/login" in joined


# --- network wrappers ------------------------------------------------------

def test_fetch_list_sorts_newest_first(monkeypatch):
    items = {"value": [
        _raw("mid", "2026-05-10T09:00:00Z", "middle"),
        _raw("new", "2026-05-11T09:00:00Z", "newest"),
        _raw("old", "2026-05-09T09:00:00Z", "oldest"),
    ]}
    monkeypatch.setattr(tui.api_mod, "api_get", lambda *a, **k: items)
    out = tui._fetch_list("https://outlook.test", "tok", "Inbox", "", False)
    assert [m["subject"] for m in out] == ["newest", "middle", "oldest"]


def test_fetch_list_none_on_failure(monkeypatch):
    monkeypatch.setattr(tui.api_mod, "api_get", lambda *a, **k: None)
    assert tui._fetch_list("https://outlook.test", "tok", "Inbox", "", False) is None


def test_set_read_issues_patch(monkeypatch):
    seen = {}

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        seen["method"] = method
        seen["body"] = body
        return {}

    monkeypatch.setattr(tui.api_mod, "api_request", fake_request)
    assert tui._set_read("https://outlook.test", "tok", "m1", False, False) is True
    assert seen["method"] == "PATCH"
    assert seen["body"]["IsRead"] is False


# --- cmd_tui guard ---------------------------------------------------------

def test_cmd_tui_refuses_non_interactive(monkeypatch):
    monkeypatch.setattr(cli.tty_mod, "is_interactive", lambda: False)
    with pytest.raises(cli.UsageError, match="interactive terminal"):
        cli.cmd_tui([], {}, "tok", "https://outlook.test")


def test_cmd_tui_launches_when_interactive(monkeypatch):
    monkeypatch.setattr(cli.tty_mod, "is_interactive", lambda: True)
    captured = {}

    def fake_run(config, token, api_base, folder="", debug=False):
        captured["folder"] = folder
        return 0

    monkeypatch.setattr("owa_mail.tui.run", fake_run)
    assert cli.cmd_tui(["--folder", "Archive"], {}, "tok", "https://outlook.test") == 0
    assert captured["folder"] == "Archive"


def test_cmd_tui_unknown_flag(monkeypatch):
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_tui(["--bogus"], {}, "tok", "https://outlook.test")
