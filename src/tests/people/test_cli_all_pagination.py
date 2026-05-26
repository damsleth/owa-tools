"""`--all` pagination tests for owa-people.

Mock a two-page Graph sequence (page 1 with @odata.nextLink, page 2
without) and assert `--all` unions the items while omitting `--all`
returns only the first page.
"""
import json

import pytest

from owa_core import http
from owa_people import cli


def _person(uid):
    return {
        "id": uid,
        "displayName": f"User {uid}",
        "mail": f"{uid}@example.com",
        "scoredEmailAddresses": [{"address": f"{uid}@example.com"}],
        "emailAddresses": [{"address": f"{uid}@example.com"}],
    }


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth",
        lambda config, debug=False: ("tok", "https://graph.test"),
    )


def _two_page_request(first_needle, page2_url, page1, page2):
    def fake_request(method, url, **kwargs):
        if page2_url in url:
            return http.Response(status=200, headers={}, json={"value": page2}, bytes=b"", next_link=None)
        if first_needle in url:
            return http.Response(status=200, headers={}, json={"value": page1}, bytes=b"", next_link=page2_url)
        raise AssertionError(f"unexpected url: {url}")
    return fake_request


def test_find_all_unions_pages(monkeypatch, capsys):
    monkeypatch.setattr(http, "request", _two_page_request(
        "me/people", "https://graph.test/people-2", [_person("u1")], [_person("u2")]
    ))
    assert cli.cmd_find(["ada", "--all"], {}, "tok", "https://graph.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["u1", "u2"]


def test_directory_all_unions_pages(monkeypatch, capsys):
    monkeypatch.setattr(http, "request", _two_page_request(
        "users?", "https://graph.test/users-2", [_person("u1")], [_person("u2"), _person("u3")]
    ))
    assert cli.cmd_directory(["norconsult", "--all"], {}, "tok", "https://graph.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["u1", "u2", "u3"]


def test_contacts_all_unions_pages(monkeypatch, capsys):
    monkeypatch.setattr(http, "request", _two_page_request(
        "me/contacts", "https://graph.test/contacts-2", [_person("u1")], [_person("u2")]
    ))
    assert cli.cmd_contacts(["--all"], {}, "tok", "https://graph.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["u1", "u2"]


def test_find_single_page_without_all(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda *a, **k: {"value": [_person("u1")], "@odata.nextLink": "https://x/next"},
    )
    assert cli.cmd_find(["ada"], {}, "tok", "https://graph.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["u1"]


def test_directory_all_recoverable_error(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "paginate_all", lambda *a, **k: None)
    assert cli.cmd_directory(["x", "--all"], {}, "tok", "https://graph.test") == 1
