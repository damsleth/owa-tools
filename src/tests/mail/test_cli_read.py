"""Tests for the `owa-mail read` recency-addressed reader."""
import json

import pytest

from owa_mail import cli


def _raw(msg_id, received, subject, body="plain body", body_type="Text"):
    return {
        "Id": msg_id,
        "ConversationId": "c-" + msg_id,
        "ReceivedDateTime": received,
        "Subject": subject,
        "From": {"EmailAddress": {"Address": "ada@example.com"}},
        "ToRecipients": [{"EmailAddress": {"Address": "bob@example.com"}}],
        "BodyPreview": "preview",
        "Body": {"ContentType": body_type, "Content": body},
        "IsRead": False,
        "HasAttachments": False,
        "Importance": "Normal",
        "Flag": {"FlagStatus": "NotFlagged"},
        "ParentFolderId": "inbox",
    }


@pytest.fixture
def page(monkeypatch):
    """Stub api_get with a deliberately out-of-order page so the command's
    client-side newest-first sort is exercised. Records the endpoint."""
    calls = []
    # Returned in mixed order; correct desc order is third, first, second.
    items = [
        _raw("mid", "2026-05-10T09:00:00Z", "middle"),
        _raw("old", "2026-05-09T09:00:00Z", "oldest"),
        _raw("new", "2026-05-11T09:00:00Z", "newest",
             body="<p>hi <a href='https://x.test/go'>link</a></p>", body_type="HTML"),
    ]

    def fake_get(api_base, endpoint, token, **kwargs):
        calls.append(endpoint)
        return {"value": items}

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    return calls


def test_latest_picks_newest_by_received(page, capsys):
    assert cli.cmd_read(["--latest"], {}, "tok", "https://outlook.test") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["subject"] == "newest"
    # read fetches the body-bearing select, so body is present.
    assert out["body"].startswith("<p>hi")


def test_default_is_latest(page, capsys):
    assert cli.cmd_read([], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["subject"] == "newest"


def test_index_selects_nth_newest(page, capsys):
    assert cli.cmd_read(["-n", "2"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["subject"] == "middle"
    assert cli.cmd_read(["--index", "3"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["subject"] == "oldest"


def test_pretty_renders_body_with_link_footnote(page, capsys):
    assert cli.cmd_read(["--latest", "--pretty"], {}, "tok", "https://outlook.test") == 0
    out = capsys.readouterr().out
    assert "Subject: newest" in out
    # HTML body flattened + the anchor URL surfaced as a footnote.
    assert "link [1]" in out
    assert "https://x.test/go" in out


def test_fetches_body_bearing_select(page):
    cli.cmd_read(["--latest"], {}, "tok", "https://outlook.test")
    # The single list fetch must request Body (so no follow-up show needed).
    assert "Body" in page[0]


def test_index_out_of_range_errors(page):
    with pytest.raises(cli.UsageError, match="only 3 match"):
        cli.cmd_read(["-n", "9"], {}, "tok", "https://outlook.test")


def test_index_below_one_errors(page):
    with pytest.raises(cli.UsageError, match=">= 1"):
        cli.cmd_read(["-n", "0"], {}, "tok", "https://outlook.test")


def test_search_and_filter_mutually_exclusive(page):
    with pytest.raises(cli.UsageError, match="--search cannot be combined"):
        cli.cmd_read(["--search", "hi", "--unread"], {}, "tok", "https://outlook.test")


def test_empty_result_errors(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {"value": []})
    with pytest.raises(cli.UsageError, match="no messages match"):
        cli.cmd_read(["--latest"], {}, "tok", "https://outlook.test")


def test_api_failure_returns_one(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_read(["--latest"], {}, "tok", "https://outlook.test") == 1


def test_unknown_flag_errors(page):
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_read(["--bogus"], {}, "tok", "https://outlook.test")
