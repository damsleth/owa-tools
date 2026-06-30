"""Tests for owa-people P2 commands: org commands, photo, groups,
contact CRUD, and the --top/--select/--filter passthrough. No network."""

import json

import pytest

from owa_core.errors import UsageError
from owa_people import cli
from owa_people.format import format_groups_pretty
from owa_people.people import normalize_group


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth",
        lambda config, debug=False: ("tok", "https://graph.test"),
    )


def _person(pid="u1", name="Ada Lovelace", mail="ada@example.com"):
    return {"id": pid, "displayName": name, "mail": mail}


# --- OData passthrough + --top alias --------------------------------------

def test_find_top_alias_and_odata_passthrough(monkeypatch):
    seen = []
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda base, ep, tok, **k: seen.append(ep) or {"value": []},
    )
    assert cli.cmd_find(
        ["ada", "--top", "7", "--select", "id,mail", "--filter", "x eq 1"],
        {}, "tok", "https://graph.test",
    ) == 0
    ep = seen[0]
    assert "%24top=7" in ep or "$top=7" in ep
    assert "select" in ep and "filter" in ep


def test_directory_select_override_and_top(monkeypatch):
    seen = []
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda base, ep, tok, **k: seen.append(ep) or {"value": []},
    )
    assert cli.cmd_directory(
        ["ada", "--top", "3", "--select", "id", "--filter", "y eq 2"],
        {}, "tok", "https://graph.test",
    ) == 0
    assert "select=id" in seen[0]


def test_contacts_top_select_filter(monkeypatch):
    seen = []
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda base, ep, tok, **k: seen.append(ep) or {"value": []},
    )
    assert cli.cmd_contacts(
        ["--top", "9", "--select", "id", "--filter", "z eq 3"],
        {}, "tok", "https://graph.test",
    ) == 0
    assert "%24top=9" in seen[0] or "$top=9" in seen[0]


# --- manager ---------------------------------------------------------------

def test_manager_defaults_to_me_json(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda base, ep, tok, **k: seen.append(ep) or _person(),
    )
    assert cli.cmd_manager([], {}, "tok", "https://graph.test") == 0
    assert seen[0] == "me/manager"
    assert json.loads(capsys.readouterr().out)["email"] == "ada@example.com"


def test_manager_target_and_pretty(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda base, ep, tok, **k: seen.append(ep) or _person(),
    )
    assert cli.cmd_manager(["bob@example.com", "--pretty"], {}, "tok", "https://graph.test") == 0
    assert seen[0] == "users/bob@example.com/manager"
    assert "Ada Lovelace" in capsys.readouterr().out


def test_manager_api_failure(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_manager([], {}, "tok", "https://graph.test") == 1


def test_manager_unknown_flag_and_extra_positional(monkeypatch):
    with pytest.raises(UsageError, match="Unknown flag"):
        cli.cmd_manager(["--bogus"], {}, "tok", "https://graph.test")
    with pytest.raises(UsageError, match="Unexpected argument"):
        cli.cmd_manager(["a", "b"], {}, "tok", "https://graph.test")


# --- direct-reports --------------------------------------------------------

def test_direct_reports_single_page(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda base, ep, tok, **k: seen.append(ep) or {"value": [_person()]},
    )
    assert cli.cmd_direct_reports([], {}, "tok", "https://graph.test") == 0
    assert seen[0] == "me/directReports"
    assert json.loads(capsys.readouterr().out)[0]["id"] == "u1"


def test_direct_reports_all_pretty(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "paginate_all", lambda *a, **k: [_person()])
    assert cli.cmd_direct_reports(["bob@x.com", "--all", "--pretty"], {}, "tok", "https://graph.test") == 0
    assert "Ada Lovelace" in capsys.readouterr().out


def test_direct_reports_failures(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_direct_reports([], {}, "tok", "https://graph.test") == 1
    monkeypatch.setattr(cli.api_mod, "paginate_all", lambda *a, **k: None)
    assert cli.cmd_direct_reports(["--all"], {}, "tok", "https://graph.test") == 1
    with pytest.raises(UsageError, match="Unknown flag"):
        cli.cmd_direct_reports(["--bogus"], {}, "tok", "https://graph.test")
    with pytest.raises(UsageError, match="Unexpected argument"):
        cli.cmd_direct_reports(["a", "b"], {}, "tok", "https://graph.test")


# --- org-chart -------------------------------------------------------------

def test_org_chart_json(monkeypatch, capsys):
    def fake_get(base, ep, tok, **k):
        if ep == "users/bob@x.com" or ep == "me":
            return _person("me", "Me", "me@x.com")
        if ep.endswith("/manager"):
            return _person("mgr", "Boss", "boss@x.com")
        if ep.endswith("/directReports"):
            return {"value": [_person("r1", "Report", "r1@x.com")]}
        return None

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    assert cli.cmd_org_chart(["bob@x.com", "--depth", "1"], {}, "tok", "https://graph.test") == 0
    chart = json.loads(capsys.readouterr().out)
    assert chart["person"]["id"] == "me"
    assert chart["managers"][0]["displayName"] == "Boss"
    assert chart["directReports"][0]["id"] == "r1"


def test_org_chart_pretty_and_top_of_chain(monkeypatch, capsys):
    def fake_get(base, ep, tok, **k):
        if ep == "me":
            return _person("me", "Me", "me@x.com")
        if ep.endswith("/manager"):
            return None  # top of chain
        if ep.endswith("/directReports"):
            return {"value": []}
        return None

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    assert cli.cmd_org_chart(["--pretty", "--depth", "5"], {}, "tok", "https://graph.test") == 0
    out = capsys.readouterr().out
    assert "* Me" in out


def test_org_chart_base_failure_and_flags(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_org_chart([], {}, "tok", "https://graph.test") == 1
    with pytest.raises(UsageError, match="Unknown flag"):
        cli.cmd_org_chart(["--bogus"], {}, "tok", "https://graph.test")
    with pytest.raises(UsageError, match="Unexpected argument"):
        cli.cmd_org_chart(["a", "b"], {}, "tok", "https://graph.test")


def test_org_chart_manager_without_id_stops(monkeypatch, capsys):
    def fake_get(base, ep, tok, **k):
        if ep == "me":
            return _person("me", "Me", "me@x.com")
        if ep.endswith("/manager"):
            return {"displayName": "Boss"}  # no id -> loop breaks
        if ep.endswith("/directReports"):
            return {"value": []}
        return None

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    assert cli.cmd_org_chart(["--depth", "3"], {}, "tok", "https://graph.test") == 0
    chart = json.loads(capsys.readouterr().out)
    assert len(chart["managers"]) == 1


# --- photo -----------------------------------------------------------------

def test_photo_to_stdout(monkeypatch, capfd):
    seen = []
    monkeypatch.setattr(
        cli.api_mod, "api_get_binary",
        lambda base, ep, tok, **k: seen.append(ep) or b"jpegbytes",
    )
    assert cli.cmd_photo([], {}, "tok", "https://graph.test") == 0
    assert seen[0] == "me/photo/$value"
    assert capfd.readouterr().out == "jpegbytes"  # binary went to stdout.buffer


def test_photo_to_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get_binary", lambda *a, **k: b"abc")
    out = tmp_path / "p.jpg"
    assert cli.cmd_photo(["bob@x.com", "--out", str(out)], {}, "tok", "https://graph.test") == 0
    assert out.read_bytes() == b"abc"
    assert "wrote 3 bytes" in capsys.readouterr().err


def test_photo_none_and_flags(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get_binary", lambda *a, **k: None)
    assert cli.cmd_photo([], {}, "tok", "https://graph.test") == 1
    with pytest.raises(UsageError, match="Unknown flag"):
        cli.cmd_photo(["--bogus"], {}, "tok", "https://graph.test")
    with pytest.raises(UsageError, match="Unexpected argument"):
        cli.cmd_photo(["a", "b"], {}, "tok", "https://graph.test")


# --- groups ----------------------------------------------------------------

def test_groups_single_page_json(monkeypatch, capsys):
    seen = []
    grp = {"@odata.type": "#microsoft.graph.group", "id": "g1",
           "displayName": "Eng", "mail": "eng@x.com", "description": "d"}
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda base, ep, tok, **k: seen.append(ep) or {"value": [grp]},
    )
    assert cli.cmd_groups([], {}, "tok", "https://graph.test") == 0
    assert seen[0].startswith("me/memberOf?")
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["type"] == "group"
    assert rows[0]["id"] == "g1"


def test_groups_all_pretty(monkeypatch, capsys):
    grp = {"@odata.type": "#microsoft.graph.group", "id": "g1", "displayName": "Eng"}
    monkeypatch.setattr(cli.api_mod, "paginate_all", lambda *a, **k: [grp])
    assert cli.cmd_groups(["bob@x.com", "--all", "--pretty", "--top", "5"], {}, "tok", "https://graph.test") == 0
    assert "Eng" in capsys.readouterr().out


def test_groups_failures(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_groups([], {}, "tok", "https://graph.test") == 1
    monkeypatch.setattr(cli.api_mod, "paginate_all", lambda *a, **k: None)
    assert cli.cmd_groups(["--all"], {}, "tok", "https://graph.test") == 1
    with pytest.raises(UsageError, match="Unknown flag"):
        cli.cmd_groups(["--bogus"], {}, "tok", "https://graph.test")
    with pytest.raises(UsageError, match="Unexpected argument"):
        cli.cmd_groups(["a", "b"], {}, "tok", "https://graph.test")


def test_normalize_group_and_format():
    g = normalize_group({"@odata.type": "#microsoft.graph.directoryRole", "id": "r"})
    assert g["type"] == "directoryRole"
    assert format_groups_pretty([]) == "(no groups)"
    assert "Eng" in format_groups_pretty([{"displayName": "Eng", "mail": "", "type": "group"}])


# --- contact CRUD ----------------------------------------------------------

def test_contact_create(monkeypatch, capsys):
    seen = {}

    def fake_req(method, base, ep, tok, body=None, **k):
        seen["method"] = method
        seen["ep"] = ep
        seen["body"] = body
        return {"id": "c1", "displayName": "Ada Lovelace",
                "emailAddresses": [{"address": "ada@example.com"}]}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_req)
    assert cli.cmd_contact_create(
        ["--name", "Ada Lovelace", "--email", "ada@example.com",
         "--given", "Ada", "--surname", "Lovelace", "--mobile", "+1",
         "--company", "AE", "--title", "Countess"],
        {}, "tok", "https://graph.test",
    ) == 0
    assert seen["method"] == "POST"
    assert seen["ep"] == "me/contacts"
    assert seen["body"]["emailAddresses"][0]["address"] == "ada@example.com"
    assert seen["body"]["givenName"] == "Ada"
    assert json.loads(capsys.readouterr().out)["id"] == "c1"


def test_contact_create_requires_field_and_failure(monkeypatch):
    with pytest.raises(UsageError, match="requires at least"):
        cli.cmd_contact_create([], {}, "tok", "https://graph.test")
    with pytest.raises(UsageError, match="Unknown flag"):
        cli.cmd_contact_create(["--bogus", "x", "--name", "a"], {}, "tok", "https://graph.test")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: None)
    assert cli.cmd_contact_create(["--name", "Ada"], {}, "tok", "https://graph.test") == 1


def test_contact_update(monkeypatch, capsys):
    seen = {}

    def fake_req(method, base, ep, tok, body=None, **k):
        seen["method"] = method
        seen["ep"] = ep
        return {"id": "c1", "displayName": "Ada"}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_req)
    assert cli.cmd_contact_update(["c1", "--title", "Countess"], {}, "tok", "https://graph.test") == 0
    assert seen["method"] == "PATCH"
    assert seen["ep"] == "me/contacts/c1"
    assert json.loads(capsys.readouterr().out)["id"] == "c1"


def test_contact_update_validation(monkeypatch, capsys):
    with pytest.raises(UsageError, match="requires a contact id"):
        cli.cmd_contact_update(["--title", "x"], {}, "tok", "https://graph.test")
    # id present but no fields -> error rc 1
    assert cli.cmd_contact_update(["c1"], {}, "tok", "https://graph.test") == 1
    assert "at least one field" in capsys.readouterr().err
    with pytest.raises(UsageError, match="Unknown flag"):
        cli.cmd_contact_update(["c1", "--bogus", "v"], {}, "tok", "https://graph.test")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: None)
    assert cli.cmd_contact_update(["c1", "--title", "x"], {}, "tok", "https://graph.test") == 1


def test_contact_delete_with_confirm(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(
        cli.api_mod, "api_request",
        lambda method, base, ep, tok, **k: seen.update(method=method, ep=ep) or {},
    )
    assert cli.cmd_contact_delete(["c1", "--confirm"], {}, "tok", "https://graph.test") == 0
    assert seen["method"] == "DELETE"
    assert seen["ep"] == "me/contacts/c1"
    assert "Deleted." in capsys.readouterr().err


def test_contact_delete_id_flag_and_failure(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: None)
    assert cli.cmd_contact_delete(["--id", "c1", "--confirm"], {}, "tok", "https://graph.test") == 1
    with pytest.raises(UsageError, match="requires a contact id"):
        cli.cmd_contact_delete([], {}, "tok", "https://graph.test")
    with pytest.raises(UsageError, match="Unknown flag"):
        cli.cmd_contact_delete(["c1", "--bogus"], {}, "tok", "https://graph.test")


def test_contact_delete_interactive_abort(monkeypatch, capsys):
    monkeypatch.setattr(cli.tty_mod, "require_confirm_or_tty", lambda **k: False)
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {"id": "c1", "displayName": "Ada"})
    monkeypatch.setattr(cli.tty_mod, "confirm", lambda *a, **k: False)
    assert cli.cmd_contact_delete(["c1"], {}, "tok", "https://graph.test") == 0
    assert "Aborted." in capsys.readouterr().err


def test_contact_delete_interactive_confirm(monkeypatch, capsys):
    monkeypatch.setattr(cli.tty_mod, "require_confirm_or_tty", lambda **k: False)
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {"id": "c1", "displayName": "Ada"})
    monkeypatch.setattr(cli.tty_mod, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: {})
    assert cli.cmd_contact_delete(["c1"], {}, "tok", "https://graph.test") == 0
    assert "Deleted." in capsys.readouterr().err


def test_contact_delete_noninteractive_refuses(monkeypatch):
    monkeypatch.setattr(
        cli.tty_mod, "require_confirm_or_tty",
        lambda **k: (_ for _ in ()).throw(UsageError("refuses")),
    )
    assert cli.cmd_contact_delete(["c1"], {}, "tok", "https://graph.test") != 0


def test_contact_delete_missing_existing(monkeypatch):
    monkeypatch.setattr(cli.tty_mod, "require_confirm_or_tty", lambda **k: False)
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_contact_delete(["c1"], {}, "tok", "https://graph.test") == 1


# --- dispatch smoke for the new commands -----------------------------------

@pytest.mark.parametrize("cmd", ["manager", "direct-reports", "org-chart", "groups"])
def test_main_dispatch_new_list_commands(monkeypatch, capsys, cmd):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda base, ep, tok, **k: {"id": "x", "value": []})
    assert cli._main([cmd]) == 0


def test_main_dispatch_photo(monkeypatch, capfd):
    monkeypatch.setattr(cli.api_mod, "api_get_binary", lambda *a, **k: b"x")
    assert cli._main(["photo"]) == 0
    assert capfd.readouterr().out == "x"


def test_main_dispatch_contact_create(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: {"id": "c1"})
    assert cli._main(["contact-create", "--name", "Ada"]) == 0


def test_main_dispatch_contact_update(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: {"id": "c1"})
    assert cli._main(["contact-update", "c1", "--title", "x"]) == 0


def test_main_dispatch_contact_delete(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: {})
    assert cli._main(["contact-delete", "c1", "--confirm"]) == 0
