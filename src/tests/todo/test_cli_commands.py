"""Direct command tests for owa-todo. No network; api_mod is stubbed."""

import json

import pytest

from owa_todo import cli


def _raw_task(task_id="t1", subject="Buy milk", status="NotStarted", importance="High"):
    return {
        "Id": task_id,
        "Subject": subject,
        "Status": status,
        "Importance": importance,
        "DueDateTime": {"DateTime": "2026-06-01T00:00:00", "TimeZone": "UTC"},
        "ParentFolderId": "f1",
        "Categories": [],
        "IsReminderOn": False,
    }


def _raw_folder(folder_id="f1", name="Tasks", default=True):
    return {"Id": folder_id, "Name": name, "IsDefaultFolder": default}


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {"default_timezone": "UTC"})
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth", lambda config, debug=False: ("tok", "https://outlook.test"),
    )


def test_lists(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda base, ep, tok, **k: {"value": [_raw_folder(), _raw_folder("f2", "Work", False)]},
    )
    assert cli.cmd_lists([], {}, "tok", "https://outlook.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["name"] for r in rows] == ["Tasks", "Work"]
    assert rows[0]["default"] is True
    assert cli.cmd_lists(["--pretty"], {}, "tok", "https://outlook.test") == 0
    assert "* Tasks" in capsys.readouterr().out


def test_tasks_all_folders_with_filters(monkeypatch, capsys):
    def fake_get(base, ep, tok, **k):
        assert ep.startswith("me/tasks")
        return {"value": [_raw_task(), _raw_task("t2", "Email Ada", "Completed", "Normal")]}

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)

    assert cli.cmd_tasks([], {}, "tok", "https://outlook.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert {r["subject"] for r in rows} == {"Buy milk", "Email Ada"}
    assert rows[0]["due"] == "2026-06-01"

    assert cli.cmd_tasks(["--status", "completed"], {}, "tok", "https://outlook.test") == 0
    assert [r["subject"] for r in json.loads(capsys.readouterr().out)] == ["Email Ada"]

    assert cli.cmd_tasks(["--search", "milk"], {}, "tok", "https://outlook.test") == 0
    assert [r["subject"] for r in json.loads(capsys.readouterr().out)] == ["Buy milk"]

    assert cli.cmd_tasks(["--pretty"], {}, "tok", "https://outlook.test") == 0
    assert "[x]" in capsys.readouterr().out


def test_tasks_by_folder_name_resolves_id(monkeypatch, capsys):
    seen = []

    def fake_get(base, ep, tok, **k):
        seen.append(ep)
        if ep == "me/taskfolders":
            return {"value": [_raw_folder("fX", "Groceries", False)]}
        return {"value": [_raw_task("t9", "Buy eggs")]}

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    assert cli.cmd_tasks(["--folder", "groceries"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)[0]["subject"] == "Buy eggs"
    assert any(ep.startswith("me/taskfolders/fX/tasks") for ep in seen)


def test_tasks_unknown_folder_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda base, ep, tok, **k: {"value": []})
    assert cli.cmd_tasks(["--folder", "nope"], {}, "tok", "https://outlook.test") == 2
    assert "no task folder" in capsys.readouterr().err


def test_create_default_folder(monkeypatch, capsys):
    seen = {}

    def fake_request(method, base, ep, tok, **k):
        seen.update(method=method, ep=ep, body=k.get("body"))
        return _raw_task("new", "Buy milk")

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    rc = cli.cmd_create(
        ["--subject", "Buy milk", "--due", "2026-06-01", "--importance", "high"],
        {"default_timezone": "UTC"}, "tok", "https://outlook.test",
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["subject"] == "Buy milk"
    assert seen["method"] == "POST"
    assert seen["ep"] == "me/tasks"
    assert seen["body"]["Subject"] == "Buy milk"
    assert seen["body"]["Importance"] == "High"
    assert seen["body"]["DueDateTime"] == {"DateTime": "2026-06-01T00:00:00", "TimeZone": "UTC"}


def test_create_into_named_folder(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda base, ep, tok, **k: {"value": [_raw_folder("fW", "Work", False)]},
    )

    def fake_request(method, base, ep, tok, **k):
        seen["ep"] = ep
        return _raw_task("n2", "Email Ada")

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli.cmd_create(
        ["--subject", "Email Ada", "--folder", "Work"],
        {"default_timezone": "UTC"}, "tok", "https://outlook.test",
    ) == 0
    capsys.readouterr()
    assert seen["ep"] == "me/taskfolders/fW/tasks"


def test_create_requires_subject():
    with pytest.raises(cli.UsageError, match="--subject is required"):
        cli.cmd_create([], {}, "tok", "https://outlook.test")


def test_update(monkeypatch, capsys):
    seen = {}

    def fake_request(method, base, ep, tok, **k):
        seen.update(method=method, ep=ep, body=k.get("body"))
        return _raw_task("t1", "Buy milk", "InProgress")

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli.cmd_update(
        ["--id", "t1", "--status", "inprogress", "--due", "2026-06-02"],
        {"default_timezone": "UTC"}, "tok", "https://outlook.test",
    ) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "InProgress"
    assert seen["method"] == "PATCH"
    assert seen["ep"] == "me/tasks/t1"
    assert seen["body"]["Status"] == "InProgress"
    assert seen["body"]["DueDateTime"]["DateTime"].startswith("2026-06-02")


def test_update_requires_id_and_fields(capsys):
    with pytest.raises(cli.UsageError, match="--id is required"):
        cli.cmd_update(["--status", "done"], {}, "tok", "https://outlook.test")
    assert cli.cmd_update(["--id", "t1"], {}, "tok", "https://outlook.test") == 1
    assert "update requires" in capsys.readouterr().err


def test_done(monkeypatch, capsys):
    seen = {}

    def fake_request(method, base, ep, tok, **k):
        seen.update(method=method, ep=ep, body=k.get("body"))
        return _raw_task("t1", "Buy milk", "Completed")

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli.cmd_done(["--id", "t1"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["status"] == "Completed"
    assert seen["body"] == {"Status": "Completed"}
    assert seen["ep"] == "me/tasks/t1"
    with pytest.raises(cli.UsageError, match="--id is required"):
        cli.cmd_done([], {}, "tok", "https://outlook.test")


def test_undone(monkeypatch, capsys):
    seen = {}

    def fake_request(method, base, ep, tok, **k):
        seen.update(method=method, ep=ep, body=k.get("body"))
        return _raw_task("t1", "Buy milk", "NotStarted")

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli.cmd_undone(["t1"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["status"] == "NotStarted"
    assert seen["body"] == {"Status": "NotStarted"}
    assert seen["ep"] == "me/tasks/t1"
    with pytest.raises(cli.UsageError, match="--id is required"):
        cli.cmd_undone([], {}, "tok", "https://outlook.test")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: None)
    assert cli.cmd_undone(["t1"], {}, "tok", "https://outlook.test") == 1


def test_create_reminder_recurrence_categories(monkeypatch, capsys):
    seen = {}

    def fake_request(method, base, ep, tok, **k):
        seen["body"] = k.get("body")
        return _raw_task("new", "Standup")

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    rc = cli.cmd_create(
        [
            "--subject", "Standup", "--recurrence", "daily",
            "--reminder", "2026-06-01T09:00",
            "--category", "work", "--category", "daily",
        ],
        {"default_timezone": "UTC"}, "tok", "https://outlook.test",
    )
    assert rc == 0
    capsys.readouterr()
    assert seen["body"]["IsReminderOn"] is True
    assert seen["body"]["Recurrence"]["Pattern"]["Type"] == "Daily"
    assert seen["body"]["Categories"] == ["work", "daily"]


def test_create_bad_recurrence_is_usage_error():
    with pytest.raises(cli.UsageError, match="--recurrence must be one of"):
        cli.cmd_create(
            ["--subject", "x", "--recurrence", "monthly"],
            {"default_timezone": "UTC"}, "tok", "https://outlook.test",
        )


def test_update_reminder_recurrence_categories(monkeypatch, capsys):
    seen = {}

    def fake_request(method, base, ep, tok, **k):
        seen["body"] = k.get("body")
        return _raw_task("t1", "x")

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    rc = cli.cmd_update(
        [
            "--id", "t1", "--reminder", "2026-06-02T08:30",
            "--recurrence", "weekly", "--category", "home",
        ],
        {"default_timezone": "UTC"}, "tok", "https://outlook.test",
    )
    assert rc == 0
    capsys.readouterr()
    assert seen["body"]["ReminderDateTime"]["DateTime"] == "2026-06-02T08:30"
    assert seen["body"]["Recurrence"]["Pattern"]["Type"] == "Weekly"
    assert seen["body"]["Categories"] == ["home"]


def test_tasks_filter_and_orderby_passthrough(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        cli, "_fetch_tasks",
        lambda endpoint, all_pages, tok, base, debug: seen.update(endpoint=endpoint) or {"value": []},
    )
    cli.cmd_tasks(
        ["--filter", "Importance eq 'High'", "--orderby", "Subject asc"],
        {}, "tok", "https://outlook.test",
    )
    assert "$filter=Importance%20eq%20%27High%27" in seen["endpoint"]
    assert "$orderby=Subject%20asc" in seen["endpoint"]


def test_list_create(monkeypatch, capsys):
    seen = {}

    def fake_request(method, base, ep, tok, **k):
        seen.update(method=method, ep=ep, body=k.get("body"))
        return _raw_folder("fN", "Groceries", False)

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli.cmd_list_create(["--name", "Groceries"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["name"] == "Groceries"
    assert seen == {"method": "POST", "ep": "me/taskfolders", "body": {"Name": "Groceries"}}
    with pytest.raises(cli.UsageError, match="--name is required"):
        cli.cmd_list_create([], {}, "tok", "https://outlook.test")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: None)
    assert cli.cmd_list_create(["--name", "x"], {}, "tok", "https://outlook.test") == 1


def test_list_rename(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda base, ep, tok, **k: {"value": [_raw_folder("fG", "Groceries", False)]},
    )

    def fake_request(method, base, ep, tok, **k):
        seen.update(method=method, ep=ep, body=k.get("body"))
        return _raw_folder("fG", "Food", False)

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli.cmd_list_rename(["Groceries", "--name", "Food"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["name"] == "Food"
    assert seen["method"] == "PATCH"
    assert seen["ep"] == "me/taskfolders/fG"
    assert seen["body"] == {"Name": "Food"}
    with pytest.raises(cli.UsageError, match="--id is required"):
        cli.cmd_list_rename(["--name", "x"], {}, "tok", "https://outlook.test")
    with pytest.raises(cli.UsageError, match="--name is required"):
        cli.cmd_list_rename(["fG"], {}, "tok", "https://outlook.test")


def test_list_rename_unknown_folder_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda base, ep, tok, **k: {"value": []})
    assert cli.cmd_list_rename(["nope", "--name", "x"], {}, "tok", "https://outlook.test") == 2
    assert "no task folder" in capsys.readouterr().err


def test_list_delete_confirm_flag(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda base, ep, tok, **k: {"value": [_raw_folder("fG", "Food", False)]},
    )

    def fake_request(method, base, ep, tok, **k):
        seen.update(method=method, ep=ep)
        return {}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli.cmd_list_delete(["Food", "--confirm"], {}, "tok", "https://outlook.test") == 0
    assert "Deleted." in capsys.readouterr().err
    assert seen == {"method": "DELETE", "ep": "me/taskfolders/fG"}
    with pytest.raises(cli.UsageError, match="--id is required"):
        cli.cmd_list_delete([], {}, "tok", "https://outlook.test")


def test_list_delete_aborts_when_declined(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "api_get",
        lambda base, ep, tok, **k: {"value": [_raw_folder("fG", "Food", False)]},
    )
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: {})
    monkeypatch.setattr(cli.tty_mod, "require_confirm_or_tty", lambda action: None)
    monkeypatch.setattr(cli.tty_mod, "confirm", lambda prompt: False)
    assert cli.cmd_list_delete(["Food"], {}, "tok", "https://outlook.test") == 0
    assert "Aborted." in capsys.readouterr().err


def test_delete_confirm_flag(monkeypatch, capsys):
    seen = {}

    def fake_request(method, base, ep, tok, **k):
        seen.update(method=method, ep=ep)
        return {}  # DELETE returns an empty body (decoded to {}).

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli.cmd_delete(["--id", "t1", "--confirm"], {}, "tok", "https://outlook.test") == 0
    assert "Deleted." in capsys.readouterr().err
    assert seen == {"method": "DELETE", "ep": "me/tasks/t1"}


def test_delete_aborts_when_declined(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda base, ep, tok, **k: _raw_task())
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: {})
    monkeypatch.setattr(cli.tty_mod, "require_confirm_or_tty", lambda action: None)
    monkeypatch.setattr(cli.tty_mod, "confirm", lambda prompt: False)
    assert cli.cmd_delete(["--id", "t1"], {}, "tok", "https://outlook.test") == 0
    assert "Aborted." in capsys.readouterr().err
    with pytest.raises(cli.UsageError, match="--id is required"):
        cli.cmd_delete([], {}, "tok", "https://outlook.test")


def test_config_and_refresh(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, "CONFIG_PATH", "/tmp/owa-todo-config")
    monkeypatch.setattr(cli.config_mod, "config_set", lambda key, value: saved.__setitem__(key, value))
    assert cli.cmd_config(["--profile", "work", "--folder", "fX"], {}) == 0
    assert saved == {"owa_piggy_profile": "work", "default_folder": "fX"}
    err = capsys.readouterr().err
    assert "default profile saved" in err and "default folder saved" in err
    assert cli.cmd_config([], {"default_timezone": "UTC"}) == 0
    assert "default_timezone=UTC" in capsys.readouterr().err

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {"DisplayName": "Ada"})
    assert cli.cmd_refresh([], {}) == 0
    assert "Authenticated as Ada" in capsys.readouterr().err
    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "")
    assert cli.cmd_refresh([], {}) == 1
    assert "Token refresh failed" in capsys.readouterr().err


def test_main_schema_version_and_unknown(capsys):
    assert cli._main(["schema"]) == 0
    assert json.loads(capsys.readouterr().out)["tool"] == "owa-todo"
    assert cli._main(["--version"]) == 0
    assert capsys.readouterr().out.startswith("owa-todo ")
    with pytest.raises(cli.UsageError, match='Unknown command'):
        cli._main(["bogus"])
