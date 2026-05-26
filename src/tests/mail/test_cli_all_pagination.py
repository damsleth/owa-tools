"""`--all` pagination tests for owa-mail.

Mock a two-page Graph-style sequence (page 1 carries @odata.nextLink,
page 2 does not) and assert `--all` returns the union of items while
omitting `--all` returns only the first page.
"""
import json

import pytest

from owa_core import http
from owa_mail import cli


def _raw_message(msg_id):
    return {
        "Id": msg_id,
        "ConversationId": "c1",
        "ReceivedDateTime": "2026-05-09T10:00:00Z",
        "SentDateTime": "2026-05-09T09:59:00Z",
        "Subject": f"Subject {msg_id}",
        "From": {"EmailAddress": {"Address": "ada@example.com"}},
        "ToRecipients": [{"EmailAddress": {"Address": "bob@example.com"}}],
        "BodyPreview": "preview",
        "Body": {"ContentType": "Text", "Content": "body"},
        "IsRead": False,
        "HasAttachments": False,
        "Importance": "Normal",
        "Flag": {"FlagStatus": "NotFlagged"},
        "ParentFolderId": "inbox",
    }


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth",
        lambda config, debug=False: ("tok", "https://outlook.test"),
    )


def _two_page_request(pages):
    """Build a fake http.request returning page 1 (with next_link) then
    page 2 (without). `pages` maps URL substrings to (value, next_link)."""
    def fake_request(method, url, **kwargs):
        for needle, (value, next_link) in pages.items():
            if needle in url:
                return http.Response(
                    status=200, headers={}, json={"value": value}, bytes=b"",
                    next_link=next_link,
                )
        raise AssertionError(f"unexpected url: {url}")
    return fake_request


def test_messages_all_unions_pages(monkeypatch, capsys):
    pages = {
        "next-page-2": ([_raw_message("m2"), _raw_message("m3")], None),
        "messages": ([_raw_message("m1")], "https://outlook.test/next-page-2"),
    }
    monkeypatch.setattr(http, "request", _two_page_request(pages))

    assert cli.cmd_messages(["--all"], {}, "tok", "https://outlook.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["m1", "m2", "m3"]


def test_messages_single_page_without_all(monkeypatch, capsys):
    def fake_get(api_base, endpoint, access_token, **kwargs):
        return {"value": [_raw_message("m1")], "@odata.nextLink": "https://x/next"}

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    assert cli.cmd_messages([], {}, "tok", "https://outlook.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["m1"]


def test_folders_all_unions_pages(monkeypatch, capsys):
    def folder(fid):
        return {"Id": fid, "DisplayName": fid, "UnreadItemCount": 0, "TotalItemCount": 0}

    pages = {
        "me/MailFolders": ([folder("Inbox")], "https://outlook.test/folders-2"),
        "folders-2": ([folder("Archive")], None),
    }
    monkeypatch.setattr(http, "request", _two_page_request(pages))

    assert cli.cmd_folders(["--all"], {}, "tok", "https://outlook.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["Inbox", "Archive"]


def test_messages_all_returns_one_on_recoverable_error(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "paginate_all", lambda *a, **k: None)
    assert cli.cmd_messages(["--all"], {}, "tok", "https://outlook.test") == 1
