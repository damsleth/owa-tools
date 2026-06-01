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
    assert "ada@example.com" in row
    assert "Hello there" in row
    # With iso8601 (default), date is 10 chars + 1 space + 3 markers + 1 space = prefix 15
    # The unread marker '*' is at index 11 (date_w=10, space=1 → prefix starts: date(10)+' '+markers)
    # prefix = date_str(10) + ' ' + marker(3) + ' '  → unread '*' at index 11
    assert row[11] == "*"


def test_list_row_read_message_has_no_unread_marker():
    msg = {"received": "2026-05-11T09:30:00Z", "from": "a@b.c",
           "subject": "x", "is_read": True}
    row = tui.list_row(msg, 80)
    # For iso8601, date width=10; unread marker '*' is at index 11
    assert row[11] == " "


def test_list_row_unread_marker_position_iso8601():
    """Unread marker is at index 11 for iso8601 date format (10 + 1 space)."""
    msg_unread = {"received": "2026-05-11T09:30:00Z", "from": "a@b.c",
                  "subject": "x", "is_read": False}
    msg_read = {"received": "2026-05-11T09:30:00Z", "from": "a@b.c",
                "subject": "x", "is_read": True}
    row_unread = tui.list_row(msg_unread, 80)
    row_read = tui.list_row(msg_read, 80)
    # iso8601 date width = 10; prefix = date(10) + ' ' + marker + flag + att + ' '
    # marker is at index 10 + 1 = 11
    assert row_unread[11] == "*"
    assert row_read[11] == " "


def test_list_row_unread_marker_position_ddmm():
    """Unread marker is at index 6 for ddmm date format (5 + 1 space)."""
    msg = {"received": "2026-05-11T09:30:00Z", "from": "a@b.c",
           "subject": "x", "is_read": False}
    row = tui.list_row(msg, 80, date_fmt='ddmm')
    # ddmm date width = 5; marker at index 5 + 1 = 6
    assert row[6] == "*"
    assert "11.05" in row


def test_list_row_unread_marker_position_ddmm_hhmm():
    """Unread marker is at index 12 for ddmm_hhmm date format (11 + 1 space)."""
    msg = {"received": "2026-05-11T09:30:00Z", "from": "a@b.c",
           "subject": "x", "is_read": False}
    row = tui.list_row(msg, 80, date_fmt='ddmm_hhmm')
    # ddmm_hhmm date width = 11; marker at index 11 + 1 = 12
    assert row[12] == "*"
    assert "11.05 09:30" in row


def test_list_row_date_format_iso8601():
    msg = {"received": "2026-05-11T09:30:00Z", "from": "a@b.c",
           "subject": "x", "is_read": True}
    row = tui.list_row(msg, 80, date_fmt='iso8601')
    assert "2026-05-11" in row


def test_list_row_date_format_ddmm():
    msg = {"received": "2026-05-11T09:30:00Z", "from": "a@b.c",
           "subject": "x", "is_read": True}
    row = tui.list_row(msg, 80, date_fmt='ddmm')
    assert "11.05" in row
    assert "2026" not in row


def test_list_row_date_format_ddmm_hhmm():
    msg = {"received": "2026-05-11T09:30:00Z", "from": "a@b.c",
           "subject": "x", "is_read": True}
    row = tui.list_row(msg, 80, date_fmt='ddmm_hhmm')
    assert "11.05 09:30" in row


def test_list_row_date_format_custom():
    msg = {"received": "2026-05-11T09:30:00Z", "from": "a@b.c",
           "subject": "x", "is_read": True}
    row = tui.list_row(msg, 80, date_fmt='custom', custom_fmt='%Y/%m/%d')
    assert "2026/05/11" in row


def test_list_row_truncates_to_narrow_width():
    msg = {"received": "2026-05-11T09:30:00Z", "from": "a@b.c",
           "subject": "x" * 200, "is_read": True}
    assert len(tui.list_row(msg, 30)) <= 30


def test_list_row_shows_date():
    """list_row includes the date field for the default iso8601 format."""
    msg = {
        "received": "2026-05-11T09:30:00Z",
        "from": "ada@example.com",
        "subject": "Hello there",
        "is_read": False,
    }
    row = tui.list_row(msg, 80)
    assert "2026-05-11" in row


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


# --- list navigation helper ------------------------------------------------

def _state(n=5):
    from owa_mail.tui_settings import Settings
    msgs = [{"id": f"m{i}", "received": f"2026-05-{10 + i:02d}T09:00:00Z"} for i in range(n)]
    return tui._State(msgs, "Inbox", Settings())


def test_move_selection_clamps_and_resets_pane_scroll():
    st = _state(5)
    st.selected = 2
    st.pane_top = 7
    tui._move_selection(st, 1)
    assert st.selected == 3
    assert st.pane_top == 0  # changing message resets pane scroll


def test_move_selection_clamps_at_bounds():
    st = _state(3)
    tui._move_selection(st, 99)
    assert st.selected == 2  # clamped to last
    tui._move_selection(st, -99)
    assert st.selected == 0  # clamped to first


def test_move_selection_no_change_keeps_pane_scroll():
    st = _state(3)
    st.selected = 0
    st.pane_top = 4
    tui._move_selection(st, -1)  # already at top, no move
    assert st.selected == 0
    assert st.pane_top == 4  # unchanged → pane scroll preserved


def test_ensure_selected_body_caches(monkeypatch):
    st = _state(3)
    st.selected = 1
    want = tui._sorted_messages(st)[1]["id"]  # account for the active sort order
    calls = []
    monkeypatch.setattr(tui, "_draw_list", lambda *a, **k: None)
    monkeypatch.setattr(
        tui, "_fetch_body",
        lambda base, tok, mid, dbg: (calls.append(mid) or {"id": mid, "body": "hi"}),
    )
    tui._ensure_selected_body(None, st, "https://outlook.test", "tok", False)
    tui._ensure_selected_body(None, st, "https://outlook.test", "tok", False)
    assert st.body_cache[want] == {"id": want, "body": "hi"}
    assert calls == [want]  # fetched once, second call hits the cache


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
