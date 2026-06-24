"""Direct command tests for owa-people."""

import json

import pytest

from owa_people import cli


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})
    monkeypatch.setattr(cli.auth_mod, "setup_auth", lambda config, debug=False: ("tok", "https://graph.test"))


def test_main_schema_and_global_profile_debug(monkeypatch, capsys):
    seen = {}

    def fake_auth(config, debug=False):
        seen["config"] = dict(config)
        seen["debug"] = debug
        return "tok", "https://graph.test"

    monkeypatch.setattr(cli.auth_mod, "setup_auth", fake_auth)
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *args, **kwargs: {"value": []})

    assert cli._main(["schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["tool"] == "owa-people"

    assert cli._main(["--debug", "--profile", "work", "find", "ada"]) == 0
    assert seen["config"]["debug"] is True
    assert seen["config"]["owa_piggy_profile"] == "work"
    assert seen["debug"] is True
    assert "DEBUG: verbose logging enabled" in capsys.readouterr().err


def test_find_directory_show_me_and_contacts(monkeypatch, capsys):
    calls = []

    def fake_get(api_base, endpoint, access_token, **kwargs):
        calls.append((api_base, endpoint, access_token, kwargs))
        if endpoint.startswith("users/ada@example.com"):
            return {
                "id": "u1",
                "displayName": "Ada Lovelace",
                "mail": "ada@example.com",
            }
        if endpoint == "me":
            return {"id": "me", "displayName": "Me", "mail": "me@example.com"}
        return {
            "value": [
                {
                    "id": "u1",
                    "displayName": "Ada Lovelace",
                    "mail": "ada@example.com",
                    "scoredEmailAddresses": [{"address": "ada@example.com"}],
                    "emailAddresses": [{"address": "ada@example.com"}],
                }
            ]
        }

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)

    assert cli.cmd_find(["ada", "--limit", "500"], {}, "tok", "https://graph.test") == 0
    people = json.loads(capsys.readouterr().out)
    assert people[0]["email"] == "ada@example.com"
    assert calls[-1][1].startswith("me/people?")
    assert "$top=100" in calls[-1][1]
    assert calls[-1][3]["extra_headers"] == {"ConsistencyLevel": "eventual"}

    assert cli.cmd_directory(["ada", "--pretty", "--limit", "0"], {}, "tok", "https://graph.test") == 0
    assert "Ada Lovelace" in capsys.readouterr().out
    assert calls[-1][1].startswith("users?")
    assert "$top=1" in calls[-1][1]

    assert cli.cmd_show(["ada@example.com", "--pretty"], {}, "tok", "https://graph.test") == 0
    assert "Ada Lovelace" in capsys.readouterr().out

    assert cli.cmd_me([], {}, "tok", "https://graph.test") == 0
    assert json.loads(capsys.readouterr().out)["id"] == "me"

    assert cli.cmd_contacts(["--search", "ada", "--pretty"], {}, "tok", "https://graph.test") == 0
    assert "Ada Lovelace" in capsys.readouterr().out
    assert calls[-1][3]["extra_headers"] == {"ConsistencyLevel": "eventual"}


def test_show_accepts_email_and_object_id(monkeypatch):
    """Graph /users accepts UPNs and object ids at the same endpoint — no branching."""
    endpoints_called = []

    def fake_get(api_base, endpoint, access_token, **kwargs):
        endpoints_called.append(endpoint)
        return {"id": "u1", "displayName": "Ada", "mail": "ada@example.com"}

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)

    assert cli.cmd_show(["ada@example.com"], {}, "tok", "https://graph.test") == 0
    assert endpoints_called[-1] == "users/ada@example.com"

    assert cli.cmd_show(["00000000-0000-0000-0000-000000000001"], {}, "tok", "https://graph.test") == 0
    assert endpoints_called[-1] == "users/00000000-0000-0000-0000-000000000001"


def test_people_validation_and_api_failures(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *args, **kwargs: None)

    with pytest.raises(cli.UsageError, match='find requires'):
        cli.cmd_find([], {}, "tok", "https://graph.test")
    with pytest.raises(cli.UsageError, match='directory requires'):
        cli.cmd_directory([], {}, "tok", "https://graph.test")
    with pytest.raises(cli.UsageError, match='show requires'):
        cli.cmd_show([], {}, "tok", "https://graph.test")
    assert cli.cmd_me([], {}, "tok", "https://graph.test") == 1
    assert cli.cmd_contacts([], {}, "tok", "https://graph.test") == 1

    with pytest.raises(cli.UsageError, match="requires an integer"):
        cli.cmd_find(["--limit", "nope", "ada"], {}, "tok", "https://graph.test")
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_contacts(["--bogus"], {}, "tok", "https://graph.test")


def test_config_and_refresh(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, "CONFIG_PATH", "/tmp/owa-people-config")
    monkeypatch.setattr(cli.config_mod, "config_set", lambda key, value: saved.setdefault(key, value))

    assert cli.cmd_config([], {"owa_piggy_profile": "work"}) == 0
    assert "owa_piggy_profile=work" in capsys.readouterr().err
    assert cli.cmd_config(["--profile", "home"], {}) == 0
    assert saved["owa_piggy_profile"] == "home"

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *args, **kwargs: {"displayName": "Ada"})
    assert cli.cmd_refresh([], {}) == 0
    assert "Authenticated as Ada" in capsys.readouterr().err

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "")
    assert cli.cmd_refresh([], {}) == 1
    assert "Token refresh failed" in capsys.readouterr().err

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *args, **kwargs: None)
    assert cli.cmd_refresh([], {}) == 1
    assert "Auth verification failed" in capsys.readouterr().err

    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_refresh(["--bogus"], {})
