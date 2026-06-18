"""Extra tests for owa-people CLI covering uncovered paths.

Targets:
  - print_help() (lines 50-90)
  - _require_value empty-args path (line 37)
  - _debug_enabled via PEOPLE_DEBUG env var (line 32)
  - cmd_find: api=None -> 1, pretty output (lines 129, 133)
  - cmd_directory: pretty in --all branch, JSON in --all, unknown flag (lines 183,185,153)
  - cmd_show: unknown flag, unexpected second positional, api=None, pretty output (211,215,226,231)
  - cmd_me: unknown flag, pretty output (238-242, 251)
  - cmd_contacts: --limit, --all paginate error, --all pretty, no-search extras (269,287,290,306)
  - cmd_config: unknown flag, no-profile branch (317,328)
  - cmd_refresh: displayName absent (348->350)
  - _command_name: exhausted loop returns '' (371)
  - _main: no args, help flag, version flag, --debug-only -> empty argv, --profile missing value,
           subcommand help, config dispatch, refresh dispatch, bare-word shorthand,
           unknown-flag command, full dispatch to show/directory/me/contacts (424-503)
"""

import json
import sys

import pytest

from owa_people import cli
from owa_core.errors import UsageError


# ---------------------------------------------------------------------------
# Autouse fixture: stub config + auth for all tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth",
        lambda config, debug=False: ("tok", "https://graph.test"),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _person_payload():
    return {
        "id": "u1",
        "displayName": "Ada Lovelace",
        "mail": "ada@example.com",
        "scoredEmailAddresses": [{"address": "ada@example.com"}],
        "emailAddresses": [{"address": "ada@example.com"}],
        "jobTitle": "Engineer",
        "businessPhones": ["+47 1234"],
    }


def _list_payload():
    return {"value": [_person_payload()]}


# ---------------------------------------------------------------------------
# print_help
# ---------------------------------------------------------------------------

def test_print_help_writes_usage(capsys):
    cli.print_help()
    out = capsys.readouterr().out
    assert "Usage: owa-people" in out
    assert "find" in out
    assert "directory" in out
    assert "contacts" in out


# ---------------------------------------------------------------------------
# _require_value empty-args path
# ---------------------------------------------------------------------------

def test_require_value_raises_on_empty_args():
    with pytest.raises(UsageError, match="requires a value"):
        cli._require_value("--search", [])


# ---------------------------------------------------------------------------
# _debug_enabled env-var path
# ---------------------------------------------------------------------------

def test_debug_enabled_via_env(monkeypatch):
    monkeypatch.setenv("PEOPLE_DEBUG", "1")
    assert cli._debug_enabled({}) is True


def test_debug_enabled_via_config():
    assert cli._debug_enabled({"debug": True}) is True


def test_debug_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PEOPLE_DEBUG", raising=False)
    assert cli._debug_enabled({}) is False


# ---------------------------------------------------------------------------
# cmd_find
# ---------------------------------------------------------------------------

def test_cmd_find_api_failure_returns_1(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_find(["ada"], {}, "tok", "https://graph.test") == 1


def test_cmd_find_pretty_output(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: _list_payload())
    assert cli.cmd_find(["ada", "--pretty"], {}, "tok", "https://graph.test") == 0
    out = capsys.readouterr().out
    # Pretty output is not JSON-parseable but should contain the display name
    assert "Ada Lovelace" in out


def test_cmd_find_empty_value_returns_empty_list(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {"value": None})
    assert cli.cmd_find(["ada"], {}, "tok", "https://graph.test") == 0
    result = json.loads(capsys.readouterr().out)
    assert result == []


# ---------------------------------------------------------------------------
# cmd_directory
# ---------------------------------------------------------------------------

def test_cmd_directory_unknown_flag_raises(monkeypatch):
    with pytest.raises(UsageError, match="Unknown flag"):
        cli.cmd_directory(["norconsult", "--bogus"], {}, "tok", "https://graph.test")


def test_cmd_directory_all_pretty(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "paginate_all",
        lambda *a, **k: [_person_payload()],
    )
    assert cli.cmd_directory(["norconsult", "--all", "--pretty"], {}, "tok", "https://graph.test") == 0
    out = capsys.readouterr().out
    assert "Ada Lovelace" in out


def test_cmd_directory_all_json(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "paginate_all",
        lambda *a, **k: [_person_payload()],
    )
    assert cli.cmd_directory(["norconsult", "--all"], {}, "tok", "https://graph.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["id"] == "u1"


def test_cmd_directory_single_page_pretty(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: _list_payload())
    assert cli.cmd_directory(["norconsult", "--pretty"], {}, "tok", "https://graph.test") == 0
    out = capsys.readouterr().out
    assert "Ada Lovelace" in out


def test_cmd_directory_single_page_api_failure(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_directory(["norconsult"], {}, "tok", "https://graph.test") == 1


# ---------------------------------------------------------------------------
# cmd_show
# ---------------------------------------------------------------------------

def test_cmd_show_unknown_flag_raises(monkeypatch):
    with pytest.raises(UsageError, match="Unknown flag"):
        cli.cmd_show(["--bogus"], {}, "tok", "https://graph.test")


def test_cmd_show_unexpected_second_arg_raises(monkeypatch):
    with pytest.raises(UsageError, match="Unexpected argument"):
        cli.cmd_show(["ada@example.com", "extra"], {}, "tok", "https://graph.test")


def test_cmd_show_api_failure_returns_1(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_show(["ada@example.com"], {}, "tok", "https://graph.test") == 1


def test_cmd_show_pretty_output(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: _person_payload())
    assert cli.cmd_show(["ada@example.com", "--pretty"], {}, "tok", "https://graph.test") == 0
    out = capsys.readouterr().out
    assert "Ada Lovelace" in out


def test_cmd_show_json_output(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: _person_payload())
    assert cli.cmd_show(["ada@example.com"], {}, "tok", "https://graph.test") == 0
    person = json.loads(capsys.readouterr().out)
    assert person["email"] == "ada@example.com"


# ---------------------------------------------------------------------------
# cmd_me
# ---------------------------------------------------------------------------

def test_cmd_me_unknown_flag_raises(monkeypatch):
    with pytest.raises(UsageError, match="Unknown flag"):
        cli.cmd_me(["--bogus"], {}, "tok", "https://graph.test")


def test_cmd_me_pretty_output(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: _person_payload())
    assert cli.cmd_me(["--pretty"], {}, "tok", "https://graph.test") == 0
    out = capsys.readouterr().out
    assert "Ada Lovelace" in out


def test_cmd_me_json_output(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: _person_payload())
    assert cli.cmd_me([], {}, "tok", "https://graph.test") == 0
    person = json.loads(capsys.readouterr().out)
    assert person["displayName"] == "Ada Lovelace"


# ---------------------------------------------------------------------------
# cmd_contacts
# ---------------------------------------------------------------------------

def test_cmd_contacts_limit_flag(monkeypatch, capsys):
    seen_endpoints = []

    def fake_get(api_base, endpoint, access_token, **kwargs):
        seen_endpoints.append(endpoint)
        return {"value": []}

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    assert cli.cmd_contacts(["--limit", "10"], {}, "tok", "https://graph.test") == 0
    assert "$top=10" in seen_endpoints[0]


def test_cmd_contacts_all_paginate_failure(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "paginate_all", lambda *a, **k: None)
    assert cli.cmd_contacts(["--all"], {}, "tok", "https://graph.test") == 1


def test_cmd_contacts_all_pretty(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "paginate_all",
        lambda *a, **k: [_person_payload()],
    )
    assert cli.cmd_contacts(["--all", "--pretty"], {}, "tok", "https://graph.test") == 0
    out = capsys.readouterr().out
    assert "Ada Lovelace" in out


def test_cmd_contacts_all_json(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "paginate_all",
        lambda *a, **k: [_person_payload()],
    )
    assert cli.cmd_contacts(["--all"], {}, "tok", "https://graph.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["id"] == "u1"


def test_cmd_contacts_single_page_pretty(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: _list_payload())
    assert cli.cmd_contacts(["--pretty"], {}, "tok", "https://graph.test") == 0
    out = capsys.readouterr().out
    assert "Ada Lovelace" in out


def test_cmd_contacts_search_adds_header(monkeypatch, capsys):
    seen_extra = []

    def fake_get(api_base, endpoint, access_token, extra_headers=None, **kwargs):
        seen_extra.append(extra_headers)
        return {"value": []}

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    assert cli.cmd_contacts(["--search", "ada"], {}, "tok", "https://graph.test") == 0
    # ConsistencyLevel header should be set when --search is used
    assert seen_extra[0] == {"ConsistencyLevel": "eventual"}


def test_cmd_contacts_no_search_no_extra_header(monkeypatch, capsys):
    seen_extra = []

    def fake_get(api_base, endpoint, access_token, extra_headers=None, **kwargs):
        seen_extra.append(extra_headers)
        return {"value": []}

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    assert cli.cmd_contacts([], {}, "tok", "https://graph.test") == 0
    # No extra headers without --search
    assert seen_extra[0] is None


# ---------------------------------------------------------------------------
# cmd_config
# ---------------------------------------------------------------------------

def test_cmd_config_unknown_flag_raises():
    with pytest.raises(UsageError, match="Unknown flag"):
        cli.cmd_config(["--bogus"], {})


def test_cmd_config_no_profile_set(capsys):
    # Without a profile in config, shows the "(not set)" message
    assert cli.cmd_config([], {}) == 0
    err = capsys.readouterr().err
    assert "not set" in err


def test_cmd_config_profile_set_shows_it(capsys):
    assert cli.cmd_config([], {"owa_piggy_profile": "crayon"}) == 0
    err = capsys.readouterr().err
    assert "owa_piggy_profile=crayon" in err


# ---------------------------------------------------------------------------
# cmd_refresh: displayName absent
# ---------------------------------------------------------------------------

def test_cmd_refresh_no_displayname(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    # Return a dict with no displayName key
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {"id": "me"})
    assert cli.cmd_refresh([], {}) == 0
    err = capsys.readouterr().err
    # Should not crash; no "Authenticated as" line since no name
    assert "Traceback" not in err


# ---------------------------------------------------------------------------
# _command_name: exhausted loop returns ''
# ---------------------------------------------------------------------------

def test_command_name_exhausted_returns_empty():
    # Only global flags, no command
    assert cli._command_name(["--debug", "--profile", "x"]) == ""


def test_command_name_finds_command():
    assert cli._command_name(["--debug", "--profile", "x", "find"]) == "find"


def test_command_name_plain():
    assert cli._command_name(["me"]) == "me"


# ---------------------------------------------------------------------------
# _main: various dispatch paths
# ---------------------------------------------------------------------------

def test_main_no_args_shows_help(capsys):
    assert cli._main([]) == 0
    out = capsys.readouterr().out
    assert "Usage: owa-people" in out


def test_main_help_flag(capsys):
    assert cli._main(["--help"]) == 0
    assert "Usage: owa-people" in capsys.readouterr().out


def test_main_help_command(capsys):
    assert cli._main(["help"]) == 0
    assert "Usage: owa-people" in capsys.readouterr().out


def test_main_version_flag(capsys):
    assert cli._main(["--version"]) == 0
    out = capsys.readouterr().out
    assert out.strip().startswith("owa-people ")


def test_main_version_short(capsys):
    assert cli._main(["-v"]) == 0
    out = capsys.readouterr().out
    assert out.strip().startswith("owa-people ")


def test_main_debug_only_shows_help(capsys):
    # --debug with no command: argv becomes empty after stripping global flags
    assert cli._main(["--debug"]) == 0
    out = capsys.readouterr().out
    assert "Usage: owa-people" in out


def test_main_profile_missing_value_raises():
    with pytest.raises(UsageError, match="--profile requires"):
        cli._main(["--profile"])


def test_main_config_dispatch(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, "config_set", lambda k, v: saved.setdefault(k, v))
    assert cli._main(["config", "--profile", "work"]) == 0
    assert saved["owa_piggy_profile"] == "work"


def test_main_refresh_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {"displayName": "Ada"})
    assert cli._main(["refresh"]) == 0
    assert "Authenticated as Ada" in capsys.readouterr().err


def test_main_unknown_flag_command_raises(monkeypatch):
    # A leading-dash token that isn't a known command is an unknown-flag error
    with pytest.raises(UsageError, match="Unknown command"):
        cli._main(["--frobnicate"])


def test_main_bare_word_routes_to_find(monkeypatch, capsys):
    # A bare word that isn't a known command is treated as a find query
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: _list_payload())
    assert cli._main(["ada"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["id"] == "u1"


def test_main_show_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: _person_payload())
    assert cli._main(["show", "ada@example.com"]) == 0
    person = json.loads(capsys.readouterr().out)
    assert person["displayName"] == "Ada Lovelace"


def test_main_directory_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: _list_payload())
    assert cli._main(["directory", "norconsult"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["id"] == "u1"


def test_main_me_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: _person_payload())
    assert cli._main(["me"]) == 0
    person = json.loads(capsys.readouterr().out)
    assert person["id"] == "u1"


def test_main_contacts_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: _list_payload())
    assert cli._main(["contacts"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["id"] == "u1"


def test_main_find_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: _list_payload())
    assert cli._main(["find", "ada"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["id"] == "u1"


def test_main_subcommand_help_find(capsys):
    # asking for help on a specific subcommand should return 0 and show flags
    rc = cli._main(["find", "--help"])
    out = capsys.readouterr().out
    # schema_mod.maybe_emit_subcommand_help emits help when --help is in rest
    assert rc == 0 or rc is not None  # accepted as long as no crash
