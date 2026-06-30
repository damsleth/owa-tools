"""Extra coverage tests for owa_sched.cli — targets previously uncovered paths.

Covers:
- _require_value missing-arg branch
- _optional_value (bare flag / value token variants)
- print_help() invocations
- cmd_availability: --month, --year, --start, --end, --interval, --pretty, unknown flag
- cmd_find_time: --from, --to, --week, --month, --year, --start, --end,
                 attendees=None (return 1), JSON output, unknown flag
- cmd_config: unknown flag branch
- cmd_refresh: extra-arg branch, no displayName path
- _command_name: empty-argv fallback
- _main dispatch: help / --help / -h, --version / -v, empty-after-filter,
                  config/refresh, unknown command, find-time
"""

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
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth",
        lambda config, debug=False: ("tok", "https://graph.test"),
    )


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def test_require_value_raises_on_empty_args():
    with pytest.raises(cli.UsageError, match="requires a value"):
        cli._require_value("--who", [])


def test_optional_value_returns_token_when_not_flag():
    """If the next token is a plain value it is consumed."""
    val, rest = cli._optional_value(["next", "--other"], "current")
    assert val == "next"
    assert rest == ["--other"]


def test_optional_value_returns_default_when_flag_follows():
    """If the next token is a flag, return default and leave args unchanged."""
    val, rest = cli._optional_value(["--pretty"], "current")
    assert val == "current"
    assert rest == ["--pretty"]


def test_optional_value_returns_default_when_empty():
    val, rest = cli._optional_value([], "current")
    assert val == "current"
    assert rest == []


# ---------------------------------------------------------------------------
# print_help
# ---------------------------------------------------------------------------

def test_print_help_outputs_usage(capsys):
    cli.print_help()
    out = capsys.readouterr().out
    assert "Usage: owa-sched" in out
    assert "availability" in out
    assert "find-time" in out


# ---------------------------------------------------------------------------
# cmd_availability — additional flag branches
# ---------------------------------------------------------------------------

def _schedule_payload():
    return {
        "value": [
            {
                "scheduleId": "a@x.com",
                "scheduleItems": [],
            }
        ]
    }


def test_availability_month_flag(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_post", lambda *a, **kw: _schedule_payload())
    rc = cli.cmd_availability(
        ["--who", "a@x.com", "--month", "5", "--year", "2026"],
        {"default_timezone": "UTC"},
        "tok", "https://graph.test",
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list)


def test_availability_start_end_interval_flags(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_post", lambda *a, **kw: _schedule_payload())
    rc = cli.cmd_availability(
        [
            "--who", "a@x.com",
            "--date", "2026-05-09",
            "--start", "08:00",
            "--end", "18:00",
            "--interval", "15",
        ],
        {"default_timezone": "UTC"},
        "tok", "https://graph.test",
    )
    assert rc == 0


def test_availability_pretty_flag(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_post", lambda *a, **kw: _schedule_payload())
    rc = cli.cmd_availability(
        ["--who", "a@x.com", "--date", "2026-05-09", "--pretty"],
        {"default_timezone": "UTC"},
        "tok", "https://graph.test",
    )
    assert rc == 0
    # pretty output goes to stdout (not stderr)
    assert capsys.readouterr().out != ""


def test_availability_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_availability(["--bogus"], {}, "tok", "https://graph.test")


def test_availability_rejects_out_of_range_interval():
    with pytest.raises(cli.UsageError, match="between 5 and 1440"):
        cli.cmd_availability(
            ["--who", "a@x.com", "--date", "2026-05-09", "--interval", "1"],
            {}, "tok", "https://graph.test",
        )


def test_availability_rejects_too_many_attendees():
    who = ",".join(f"u{i}@x.com" for i in range(21))
    with pytest.raises(cli.UsageError, match="at most 20 attendees"):
        cli.cmd_availability(
            ["--who", who, "--date", "2026-05-09"],
            {}, "tok", "https://graph.test",
        )


def test_availability_tz_override_passed_to_get_schedule(monkeypatch):
    seen = {}

    def fake_post(base, endpoint, token, body=None, debug=False):
        seen["tz"] = body["startTime"]["timeZone"]
        return _schedule_payload()

    monkeypatch.setattr(cli.api_mod, "api_post", fake_post)
    rc = cli.cmd_availability(
        ["--who", "a@x.com", "--date", "2026-05-09", "--tz", "UTC"],
        {"default_timezone": "W. Europe Standard Time"},
        "tok", "https://graph.test",
    )
    assert rc == 0
    assert seen["tz"] == "UTC"


# ---------------------------------------------------------------------------
# cmd_find_time — additional flag branches and return paths
# ---------------------------------------------------------------------------

def test_find_time_from_to_week_flags(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_post", lambda *a, **kw: _schedule_payload())
    rc = cli.cmd_find_time(
        [
            "--who", "a@x.com",
            "--from", "2026-05-05",
            "--to", "2026-05-09",
            "--duration", "30",
        ],
        {"default_timezone": "UTC"},
        "tok", "https://graph.test",
    )
    assert rc == 0
    slots = json.loads(capsys.readouterr().out)
    assert isinstance(slots, list)


def test_find_time_week_month_year_start_end_flags(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_post", lambda *a, **kw: _schedule_payload())
    rc = cli.cmd_find_time(
        [
            "--who", "a@x.com",
            "--week", "19",
            "--year", "2026",
            "--start", "09:00",
            "--end", "17:00",
        ],
        {"default_timezone": "UTC"},
        "tok", "https://graph.test",
    )
    assert rc == 0


def test_find_time_month_bare_flag(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_post", lambda *a, **kw: _schedule_payload())
    rc = cli.cmd_find_time(
        ["--who", "a@x.com", "--month", "--pretty"],
        {"default_timezone": "UTC"},
        "tok", "https://graph.test",
    )
    assert rc == 0
    # pretty path: "Open slots:" text
    assert "Open slots" in capsys.readouterr().out


def test_find_time_returns_1_when_api_returns_none(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_post", lambda *a, **kw: None)
    rc = cli.cmd_find_time(
        ["--who", "a@x.com", "--date", "2026-05-09"],
        {"default_timezone": "UTC"},
        "tok", "https://graph.test",
    )
    assert rc == 1


def test_find_time_json_output_no_pretty(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_post", lambda *a, **kw: _schedule_payload())
    rc = cli.cmd_find_time(
        ["--who", "a@x.com", "--date", "2026-05-09"],
        {"default_timezone": "UTC"},
        "tok", "https://graph.test",
    )
    assert rc == 0
    out = capsys.readouterr().out.strip()
    # Should be valid JSON list
    data = json.loads(out)
    assert isinstance(data, list)


def test_find_time_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_find_time(["--nope"], {}, "tok", "https://graph.test")


# ---------------------------------------------------------------------------
# cmd_config — unknown flag branch
# ---------------------------------------------------------------------------

def test_config_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_config(["--unknown-flag"], {})


def test_config_no_profile_set_prints_defaults(capsys):
    # Branch: no owa_piggy_profile in config
    rc = cli.cmd_config([], {"default_timezone": "Europe/Oslo"})
    assert rc == 0
    err = capsys.readouterr().err
    assert "owa_piggy_profile=(not set" in err


# ---------------------------------------------------------------------------
# cmd_refresh — error branches
# ---------------------------------------------------------------------------

def test_refresh_raises_on_extra_arg():
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_refresh(["--extra"], {})


def test_refresh_no_displayname_still_succeeds(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **kw: {"id": "abc"})
    rc = cli.cmd_refresh([], {})
    assert rc == 0
    # No "Authenticated as" line, but no error either
    out = capsys.readouterr()
    assert "Authenticated as" not in out.err


# ---------------------------------------------------------------------------
# _command_name — fallback to empty string
# ---------------------------------------------------------------------------

def test_command_name_returns_empty_for_no_real_token():
    assert cli._command_name([]) == ""
    assert cli._command_name(["--debug", "--verbose"]) == ""
    assert cli._command_name(["--profile", "work"]) == ""


def test_command_name_skips_profile_value():
    assert cli._command_name(["--profile", "work", "availability"]) == "availability"


# ---------------------------------------------------------------------------
# _main dispatch paths
# ---------------------------------------------------------------------------

def test_main_help_flag(capsys):
    assert cli._main(["help"]) == 0
    assert "Usage: owa-sched" in capsys.readouterr().out


def test_main_double_help_flag(capsys):
    assert cli._main(["--help"]) == 0
    assert "Usage: owa-sched" in capsys.readouterr().out


def test_main_h_flag(capsys):
    assert cli._main(["-h"]) == 0
    assert "Usage: owa-sched" in capsys.readouterr().out


def test_main_version_flag(capsys):
    assert cli._main(["--version"]) == 0
    assert "owa-sched" in capsys.readouterr().out


def test_main_v_flag(capsys):
    assert cli._main(["-v"]) == 0
    assert "owa-sched" in capsys.readouterr().out


def test_main_empty_after_filter(capsys):
    # --debug alone strips to empty argv -> help printed
    assert cli._main(["--debug"]) == 0
    assert "Usage: owa-sched" in capsys.readouterr().out


def test_main_config_dispatch(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, "config_set", lambda k, v: saved.setdefault(k, v))
    rc = cli._main(["config", "--profile", "home"])
    assert rc == 0
    assert saved["owa_piggy_profile"] == "home"


def test_main_refresh_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **kw: {"displayName": "Bob"})
    rc = cli._main(["refresh"])
    assert rc == 0
    assert "Authenticated as Bob" in capsys.readouterr().err


def test_main_unknown_command_raises():
    with pytest.raises(cli.UsageError, match="Unknown command"):
        cli._main(["frobnicate"])


def test_main_find_time_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_post", lambda *a, **kw: _schedule_payload())
    rc = cli._main([
        "find-time",
        "--who", "a@x.com",
        "--date", "2026-05-09",
    ])
    assert rc == 0


def test_main_availability_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_post", lambda *a, **kw: _schedule_payload())
    rc = cli._main([
        "availability",
        "--who", "a@x.com",
        "--date", "2026-05-09",
    ])
    assert rc == 0


def test_main_profile_override_passed_to_config(monkeypatch, capsys):
    seen = {}

    def fake_auth(config, debug=False):
        seen["profile"] = config.get("owa_piggy_profile")
        return "tok", "https://graph.test"

    monkeypatch.setattr(cli.auth_mod, "setup_auth", fake_auth)
    monkeypatch.setattr(cli.api_mod, "api_post", lambda *a, **kw: _schedule_payload())
    cli._main(["--profile", "myprofile", "availability", "--who", "a@x.com", "--date", "2026-05-09"])
    assert seen["profile"] == "myprofile"
