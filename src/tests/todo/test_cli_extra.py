"""Coverage for owa-todo dispatch, help, global flags, and error paths."""
import json
from datetime import date

import pytest

from owa_core.auth import BrokerProfile
from owa_todo import cli


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {"default_timezone": "UTC"})
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth", lambda config, debug=False: ("tok", "https://outlook.test"),
    )


def test_help_and_no_args(capsys):
    assert cli._main([]) == 0
    assert "owa-todo" in capsys.readouterr().out
    assert cli._main(["help"]) == 0
    assert "Commands:" in capsys.readouterr().out


def test_profile_only_main_defaults_to_tasks_and_merges_json(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {"value": []})

    assert cli.main(["--profile", "work", "--profile", "home"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["_owa"]["command"] == "tasks"
    assert payload["_owa"]["profiles"] == ["work", "home"]
    assert payload["results"] == [
        {"profile": "work", "ok": True, "data": []},
        {"profile": "home", "ok": True, "data": []},
    ]


def test_all_profile_main_defaults_to_tasks_and_returns_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "owa_core.auth.get_profiles",
        lambda **kwargs: [
            BrokerProfile("work", True, True, True),
            BrokerProfile("home", False, True, True),
        ],
    )
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {"value": []})

    assert cli.main(["--profile", "all"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["_owa"]["command"] == "tasks"
    assert payload["_owa"]["profiles"] == ["work", "home"]
    assert all(result["ok"] for result in payload["results"])


@pytest.mark.parametrize("profile_args", [["-A"], ["--all-profiles"]])
def test_all_profile_aliases_default_to_tasks(profile_args):
    assert cli._default_profile_command(profile_args) == [*profile_args, "tasks"]


def test_subcommand_help_renders_required_marker(capsys):
    assert cli._main(["create", "--help"]) == 0
    out = capsys.readouterr().out
    assert "owa-todo create" in out
    assert "(required)" in out


def test_debug_flag_enables_logging(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda base, ep, tok, **k: {"value": []})
    assert cli._main(["--debug", "lists"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == []
    assert "DEBUG" in captured.err


def test_profile_override_reaches_auth(monkeypatch, capsys):
    seen = {}

    def fake_setup(config, debug=False):
        seen["profile"] = config.get("owa_piggy_profile")
        return "tok", "https://outlook.test"

    monkeypatch.setattr(cli.auth_mod, "setup_auth", fake_setup)
    monkeypatch.setattr(cli.api_mod, "api_get", lambda base, ep, tok, **k: {"value": []})
    assert cli._main(["--profile", "work", "tasks"]) == 0
    capsys.readouterr()
    assert seen["profile"] == "work"


def test_lists_all_pagination(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "paginate_all",
        lambda base, ep, tok, **k: [{"Id": "f1", "Name": "Tasks", "IsDefaultFolder": True}],
    )
    assert cli.cmd_lists(["--all"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)[0]["name"] == "Tasks"


def test_tasks_all_pagination(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "paginate_all",
        lambda base, ep, tok, **k: [{"Id": "t1", "Subject": "x", "Status": "NotStarted"}],
    )
    assert cli.cmd_tasks(["--all"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)[0]["subject"] == "x"


def test_tasks_limit_must_be_int():
    with pytest.raises(cli.UsageError, match="requires an integer"):
        cli.cmd_tasks(["--limit", "abc"], {}, "tok", "https://outlook.test")


def test_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_lists(["--bogus"], {}, "tok", "https://outlook.test")


def test_main_dispatches_new_commands(monkeypatch, capsys):
    # Route undone / list-create / list-rename / list-delete through _main so
    # the dispatch arms are exercised end to end.
    monkeypatch.setattr(
        cli.api_mod, "api_request",
        lambda method, base, ep, tok, **k: {"Id": "f1", "Name": "L", "Status": "NotStarted"},
    )
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda base, ep, tok, **k: {"value": [{"Id": "f1", "Name": "L", "IsDefaultFolder": False}]},
    )
    assert cli._main(["undone", "t1"]) == 0
    capsys.readouterr()
    assert cli._main(["list-create", "--name", "L"]) == 0
    capsys.readouterr()
    assert cli._main(["list-rename", "L", "--name", "L2"]) == 0
    capsys.readouterr()
    assert cli._main(["list-delete", "L", "--confirm"]) == 0
    assert "Deleted." in capsys.readouterr().err


def test_resolve_date():
    assert cli._resolve_date("today") == date.today().strftime("%Y-%m-%d")
    assert cli._resolve_date("2026-01-01") == "2026-01-01"


def test_recoverable_api_errors_return_1(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_lists([], {}, "tok", "https://outlook.test") == 1
    assert cli.cmd_tasks([], {}, "tok", "https://outlook.test") == 1

    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: None)
    assert cli.cmd_create(["--subject", "x"], {"default_timezone": "UTC"}, "tok", "https://outlook.test") == 1
    assert cli.cmd_done(["--id", "t1"], {}, "tok", "https://outlook.test") == 1
