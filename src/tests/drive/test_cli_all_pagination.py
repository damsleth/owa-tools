"""`--all` pagination tests for owa-drive.

Mock a two-page Graph sequence (page 1 with @odata.nextLink, page 2
without) and assert `--all` unions the items while omitting `--all`
returns only the first page.
"""
import json

import pytest

from owa_core import http
from owa_drive import cli


def _item(name):
    return {
        "id": name,
        "name": name,
        "size": 1,
        "lastModifiedDateTime": "2026-05-09T12:00:00Z",
        "webUrl": "https://example.test/item",
        "parentReference": {"path": "/drive/root:/Documents"},
        "file": {"mimeType": "text/plain"},
    }


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth",
        lambda config, debug=False: ("tok", "https://graph.test"),
    )


def test_ls_all_unions_pages(monkeypatch, capsys):
    page2_url = "https://graph.test/children-2"

    def fake_request(method, url, **kwargs):
        if "children-2" in url:
            return http.Response(status=200, headers={}, json={"value": [_item("b.txt")]}, bytes=b"", next_link=None)
        if "children" in url:
            return http.Response(status=200, headers={}, json={"value": [_item("a.txt")]}, bytes=b"", next_link=page2_url)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(http, "request", fake_request)
    assert cli.cmd_ls(["--all"], {}, "tok", "https://graph.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["name"] for r in rows] == ["a.txt", "b.txt"]


def test_ls_single_page_without_all(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "api_request",
        lambda *a, **k: {"value": [_item("a.txt")], "@odata.nextLink": "https://x/next"},
    )
    assert cli.cmd_ls([], {}, "tok", "https://graph.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["name"] for r in rows] == ["a.txt"]


def test_ls_all_recoverable_error(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "paginate_all", lambda *a, **k: None)
    assert cli.cmd_ls(["--all"], {}, "tok", "https://graph.test") == 1
