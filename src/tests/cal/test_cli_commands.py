"""Direct command tests for owa-cal."""

import json

import pytest

from owa_cal import cli


def _raw_event(event_id="e1", subject="Planning", start="2026-05-09T09:00:00", end="2026-05-09T10:00:00"):
    return {
        "Id": event_id,
        "Subject": subject,
        "Start": {"DateTime": start, "TimeZone": "UTC"},
        "End": {"DateTime": end, "TimeZone": "UTC"},
        "Categories": ["Blue"],
        "Location": {"DisplayName": "Room"},
        "ShowAs": "Busy",
        "IsAllDay": False,
    }


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {"default_timezone": "UTC"})
    monkeypatch.setattr(cli.auth_mod, "setup_auth", lambda config, debug=False: ("tok", "https://outlook.test"))


def test_main_schema_webcal_and_source_resolution(monkeypatch, capsys):
    assert cli._main(["schema"]) == 0
    assert json.loads(capsys.readouterr().out)["tool"] == "owa-cal"

    monkeypatch.setattr(cli.profiles_mod, "load_local", lambda: {"feed": {"webcal_url": "https://feed.test/ical"}})
    monkeypatch.setattr(cli.profiles_mod, "piggy_aliases", lambda: ({"feed"}, "feed"))
    assert cli._resolve_source({"owa_piggy_profile": "feed"}) == ("webcal", "https://feed.test/ical")
    assert "also an owa-piggy profile" in capsys.readouterr().err

    monkeypatch.setattr(cli.profiles_mod, "load_local", lambda: {})
    assert cli._resolve_source({"owa_piggy_profile": "work"}) == ("oauth", "work")
    monkeypatch.setenv("OWA_CAL_WEBCAL_URL", "https://env-feed.test/ical")
    assert cli._resolve_source({}) == ("webcal", "https://env-feed.test/ical")

    monkeypatch.setattr(cli.ics_mod, "fetch_and_normalize", lambda url: [
        {"id": "1", "subject": "Planning", "start": "2026-05-09T09:00:00", "end": "2026-05-09T10:00:00"},
        {"id": "2", "subject": "Other", "start": "2026-05-10T09:00:00", "end": "2026-05-10T10:00:00"},
    ])
    assert cli.cmd_events_webcal(["--date", "2026-05-09", "--search", "plan"], {"webcal_url": "x"}, ) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [row["id"] for row in rows] == ["1"]

    monkeypatch.setattr(cli.ics_mod, "fetch_and_normalize", lambda url: (_ for _ in ()).throw(OSError("bad")))
    assert cli.cmd_events_webcal([], {"webcal_url": "x"}) == 1
    assert "failed to fetch webcal feed" in capsys.readouterr().err


def test_events_create_update_delete_categories(monkeypatch, capsys):
    requests = []

    def fake_get(api_base, endpoint, access_token, **kwargs):
        if endpoint.startswith("me/calendarView"):
            return {"value": [_raw_event(), _raw_event("e2")]}
        if endpoint.startswith("me/events/"):
            return _raw_event()
        if endpoint == "me/MasterCategories":
            return {"value": [{"DisplayName": "Blue", "Color": "Preset0"}]}
        return {"value": []}

    def fake_request(method, api_base, endpoint, access_token, **kwargs):
        requests.append((method, endpoint, kwargs.get("body")))
        if method == "DELETE":
            return {}
        if endpoint == "me/MasterCategories":
            return {"DisplayName": "Green", "Color": "Preset0"}
        if method == "PATCH":
            return _raw_event("e1", "Updated")
        return _raw_event("new", "Created")

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)

    assert cli.cmd_events(["--date", "2026-05-09", "--search", "Planning"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)[0]["subject"] == "Planning"

    assert cli.cmd_create([
        "--subject",
        "Created",
        "--date",
        "2026-05-09",
        "--start",
        "09:00",
        "--end",
        "10:00",
        "--category",
        "Blue",
        "--location",
        "Room",
        "--body",
        "notes",
        "--showas",
        "Tentative",
    ], {"default_timezone": "UTC"}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["subject"] == "Created"
    assert requests[-1][1] == "me/events"
    assert requests[-1][2]["Categories"] == ["Blue"]

    assert cli.cmd_create(["--subject", "All day", "--date", "2026-05-09", "--allday"], {}, "tok", "https://outlook.test") == 0
    capsys.readouterr()
    assert requests[-1][2]["IsAllDay"] is True
    assert requests[-1][2]["End"]["DateTime"].startswith("2026-05-10")

    assert cli.cmd_update(["--id", "e1", "--date", "2026-05-10", "--start", "11:00"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["subject"] == "Updated"
    assert requests[-1][0] == "PATCH"
    assert requests[-1][2]["Start"]["DateTime"].startswith("2026-05-10T11:00")

    assert cli.cmd_update(["--id", "e1"], {}, "tok", "https://outlook.test") == 1
    assert "update requires" in capsys.readouterr().err

    assert cli.cmd_delete(["--id", "e1", "--confirm"], {}, "tok", "https://outlook.test") == 0
    assert "Deleted." in capsys.readouterr().err

    assert cli.cmd_categories([], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out) == [{"name": "Blue", "color": "Preset0"}]
    assert cli.cmd_categories(["--pretty"], {}, "tok", "https://outlook.test") == 0
    assert "Blue" in capsys.readouterr().out
    assert cli.cmd_categories(["--add", "Green"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["DisplayName"] == "Green"


def test_cal_validation_confirm_profiles_and_refresh(monkeypatch, capsys):
    with pytest.raises(cli.UsageError, match="--subject is required"):
        cli.cmd_create([], {}, "tok", "https://outlook.test")
    with pytest.raises(cli.UsageError, match="--id is required"):
        cli.cmd_delete([], {}, "tok", "https://outlook.test")

    monkeypatch.setattr(cli.api_mod, "api_get", lambda *args, **kwargs: _raw_event())
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *args, **kwargs: {})
    monkeypatch.setattr(cli.tty_mod, "require_confirm_or_tty", lambda action: None)
    monkeypatch.setattr(cli.tty_mod, "confirm", lambda prompt: False)
    assert cli.cmd_delete(["--id", "e1"], {}, "tok", "https://outlook.test") == 0
    assert "Aborted." in capsys.readouterr().err

    local = {"feed": {"webcal_url": "secret"}, "shadow": {"webcal_url": "secret"}}
    monkeypatch.setattr(cli.profiles_mod, "load_local", lambda: local)
    monkeypatch.setattr(cli.profiles_mod, "piggy_aliases", lambda: ({"shadow", "work"}, "work"))
    assert cli.cmd_profiles(["--pretty"], {}) == 0
    assert "shadowed by owa-cal" in capsys.readouterr().out
    assert cli.cmd_profiles([], {}) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["source"] == "owa-cal"

    monkeypatch.setattr(cli.profiles_mod, "add_local", lambda alias, webcal: True)
    assert cli.cmd_profiles(["add", "feed", "--webcal", "https://feed.test"], {}) == 0
    assert "created" in capsys.readouterr().err
    assert cli.cmd_profiles(["add"], {}) == 1
    assert "requires an <alias>" in capsys.readouterr().err
    assert cli.cmd_profiles(["add", "feed"], {}) == 1
    assert "requires --webcal" in capsys.readouterr().err

    monkeypatch.setattr(cli.profiles_mod, "delete_local", lambda alias: alias == "feed")
    assert cli.cmd_profiles(["delete", "feed"], {}) == 0
    assert "removed" in capsys.readouterr().err
    assert cli.cmd_profiles(["delete", "work"], {}) == 2
    assert "owa-piggy profile" in capsys.readouterr().err
    assert cli.cmd_profiles(["delete", "missing"], {}) == 1
    assert "no owa-cal profile" in capsys.readouterr().err

    saved = {}
    monkeypatch.setattr(cli.config_mod, "CONFIG_PATH", "/tmp/owa-cal-config")
    monkeypatch.setattr(cli.config_mod, "config_set", lambda key, value: saved.setdefault(key, value))
    assert cli.cmd_config(["--profile", "home"], {}) == 0
    assert saved["owa_piggy_profile"] == "home"
    assert cli.cmd_config([], {"owa_piggy_profile": "work", "default_timezone": "UTC"}) == 0
    assert "default_timezone=UTC" in capsys.readouterr().err

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *args, **kwargs: {"DisplayName": "Ada"})
    assert cli.cmd_refresh([], {}) == 0
    assert "Authenticated as Ada" in capsys.readouterr().err
    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "")
    assert cli.cmd_refresh([], {}) == 1
    assert "Token refresh failed" in capsys.readouterr().err
