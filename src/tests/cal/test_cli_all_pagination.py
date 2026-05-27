"""`--all` pagination tests for owa-cal `events`.

Mock a two-page calendarView sequence (page 1 with @odata.nextLink,
page 2 without) and assert `--all` unions the events while omitting
`--all` returns only the first page.
"""
import json

import pytest

from owa_cal import cli
from owa_core import http


def _raw_event(event_id):
    return {
        "Id": event_id,
        "Subject": f"Event {event_id}",
        "Start": {"DateTime": "2026-05-09T09:00:00", "TimeZone": "UTC"},
        "End": {"DateTime": "2026-05-09T10:00:00", "TimeZone": "UTC"},
        "Categories": [],
        "Location": {"DisplayName": "Room"},
        "ShowAs": "Busy",
        "IsAllDay": False,
    }


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {"default_timezone": "UTC"})
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth",
        lambda config, debug=False: ("tok", "https://outlook.test"),
    )
    # Force the OAuth path (no local webcal profile).
    monkeypatch.setattr(cli.profiles_mod, "load_local", lambda: {})
    monkeypatch.setattr(cli.profiles_mod, "piggy_aliases", lambda: (set(), ""))


def test_events_all_unions_pages(monkeypatch, capsys):
    page2_url = "https://outlook.test/calview-2"

    def fake_request(method, url, **kwargs):
        if "calview-2" in url:
            return http.Response(status=200, headers={}, json={"value": [_raw_event("e2")]}, bytes=b"", next_link=None)
        if "calendarView" in url:
            return http.Response(status=200, headers={}, json={"value": [_raw_event("e1")]}, bytes=b"", next_link=page2_url)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(http, "request", fake_request)
    assert cli.cmd_events(["--all"], {}, "tok", "https://outlook.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["e1", "e2"]


def test_events_single_page_without_all(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda *a, **k: {"value": [_raw_event("e1")], "@odata.nextLink": "https://x/next"},
    )
    assert cli.cmd_events([], {}, "tok", "https://outlook.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["e1"]


def test_events_all_recoverable_error(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "paginate_all", lambda *a, **k: None)
    assert cli.cmd_events(["--all"], {}, "tok", "https://outlook.test") == 1


def test_events_webcal_accepts_all_noop(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.ics_mod, "fetch_and_normalize",
        lambda url: [{"subject": "Webcal", "start": "2026-05-09T09:00:00", "end": "2026-05-09T10:00:00"}],
    )
    rc = cli.cmd_events_webcal(["--all"], {"webcal_url": "https://feed.test/ical"})
    assert rc == 0
