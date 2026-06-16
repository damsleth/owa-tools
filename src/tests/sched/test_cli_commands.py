"""Direct command tests for owa-sched."""

import json

import pytest

from owa_sched import cli


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {
        "default_timezone": "UTC",
        "default_work_start": "09:00",
        "default_work_end": "17:00",
    })
    monkeypatch.setattr(cli.auth_mod, "setup_auth", lambda config, debug=False: ("tok", "https://graph.test"))


def _schedule_payload():
    return {
        "value": [
            {
                "scheduleId": "ada@example.com",
                "scheduleItems": [
                    {
                        "status": "busy",
                        "start": {"dateTime": "2026-05-09T10:00:00"},
                        "end": {"dateTime": "2026-05-09T11:00:00"},
                        "subject": "Focus",
                    },
                    {
                        "status": "free",
                        "start": {"dateTime": "2026-05-09T12:00:00"},
                        "end": {"dateTime": "2026-05-09T13:00:00"},
                    },
                ],
            }
        ]
    }


def test_resolve_window_week_is_mon_fri():
    """owa-sched weeks are Mon-Fri (work week), unlike owa-cal's Mon-Sun."""
    start, end = cli._resolve_window('', '', '', '19', '', '2026')
    assert start == '2026-05-04'  # Monday
    assert end == '2026-05-08'    # Friday


def test_resolve_window_month_full_calendar_month():
    start, end = cli._resolve_window('', '', '', '', '3', '2026')
    assert start == '2026-03-01'
    assert end == '2026-03-31'


def test_resolve_window_conflicting_period_flags():
    with pytest.raises(cli.UsageError):
        cli._resolve_window('', '', '', '19', 'current', '')


def test_main_schema_profile_and_debug(monkeypatch, capsys):
    seen = {}

    def fake_auth(config, debug=False):
        seen["config"] = dict(config)
        seen["debug"] = debug
        return "tok", "https://graph.test"

    monkeypatch.setattr(cli.auth_mod, "setup_auth", fake_auth)
    monkeypatch.setattr(cli.api_mod, "api_post", lambda *args, **kwargs: _schedule_payload())

    assert cli._main(["schema"]) == 0
    assert json.loads(capsys.readouterr().out)["tool"] == "owa-sched"

    assert cli._main([
        "--debug",
        "--profile",
        "work",
        "availability",
        "--who",
        "ada@example.com",
        "--date",
        "2026-05-09",
    ]) == 0
    assert seen["config"]["debug"] is True
    assert seen["config"]["owa_piggy_profile"] == "work"
    assert seen["debug"] is True


def test_availability_and_find_time(monkeypatch, capsys):
    calls = []

    def fake_post(api_base, endpoint, access_token, *, body, debug=False):
        calls.append((api_base, endpoint, access_token, body, debug))
        return _schedule_payload()

    monkeypatch.setattr(cli.api_mod, "api_post", fake_post)
    config = {"default_timezone": "UTC", "default_work_start": "09:00", "default_work_end": "12:00"}

    assert cli.cmd_availability([
        "--who",
        "ada@example.com,bob@example.com",
        "--from",
        "2026-05-09",
        "--to",
        "2026-05-10",
        "--start",
        "08:30",
        "--end",
        "17:30",
        "--interval",
        "15",
    ], config, "tok", "https://graph.test") == 0
    attendees = json.loads(capsys.readouterr().out)
    assert attendees[0]["busy"][0]["subject"] == "Focus"
    assert calls[-1][3]["schedules"] == ["ada@example.com", "bob@example.com"]
    assert calls[-1][3]["availabilityViewInterval"] == 15

    assert cli.cmd_find_time([
        "--who",
        "ada@example.com",
        "--date",
        "2026-05-09",
        "--duration",
        "30",
        "--pretty",
    ], config, "tok", "https://graph.test") == 0
    assert "Open slots:" in capsys.readouterr().out
    assert calls[-1][3]["availabilityViewInterval"] == 15


def test_sched_validation_and_failures(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_post", lambda *args, **kwargs: None)

    with pytest.raises(cli.UsageError, match='--who is required'):
        cli.cmd_availability([], {}, "tok", "https://graph.test")
    with pytest.raises(cli.UsageError, match='--who is required'):
        cli.cmd_find_time([], {}, "tok", "https://graph.test")
    with pytest.raises(cli.UsageError, match='--duration must be positive'):
        cli.cmd_find_time(["--who", "ada@example.com", "--duration", "0"], {}, "tok", "https://graph.test")
    assert cli.cmd_availability(["--who", "ada@example.com"], {}, "tok", "https://graph.test") == 1

    with pytest.raises(cli.UsageError, match="requires an integer"):
        cli.cmd_availability(["--who", "ada@example.com", "--interval", "x"], {}, "tok", "https://graph.test")
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_find_time(["--bogus"], {}, "tok", "https://graph.test")


def test_sched_config_and_refresh(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, "CONFIG_PATH", "/tmp/owa-sched-config")
    monkeypatch.setattr(cli.config_mod, "config_set", lambda key, value: saved.setdefault(key, value))

    assert cli.cmd_config([], {"owa_piggy_profile": "work", "default_timezone": "UTC"}) == 0
    err = capsys.readouterr().err
    assert "owa_piggy_profile=work" in err
    assert "default_timezone=UTC" in err
    assert cli.cmd_config(["--profile", "home"], {}) == 0
    assert saved["owa_piggy_profile"] == "home"

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *args, **kwargs: {"displayName": "Ada"})
    assert cli.cmd_refresh([], {}) == 0
    assert "Authenticated as Ada" in capsys.readouterr().err

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "")
    assert cli.cmd_refresh([], {}) == 1
    assert "Token refresh failed" in capsys.readouterr().err

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *args, **kwargs: None)
    assert cli.cmd_refresh([], {}) == 1
    assert "Auth verification failed" in capsys.readouterr().err
