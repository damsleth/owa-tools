import json
from types import SimpleNamespace

import pytest

from owa_core.errors import ExitCode
from owa_swodp import cli

CAPTURED = SimpleNamespace(
    instance="prod",
    host="swodp.example.invalid",
    user="user@example.invalid",
)


def test_status_probes_api(tmp_path, monkeypatch, capsys):
    profile = tmp_path / "edge-profile"
    profile.mkdir()
    monkeypatch.setattr(cli.session_mod, "profile_dir", lambda instance: profile)
    monkeypatch.setattr(cli, "_capture", lambda *a, **k: CAPTURED)
    monkeypatch.setattr(cli.service, "probe", lambda *a, **k: 1)
    assert cli.main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["probe_rows"] == 1


def test_sync_emits_json_and_agent_envelope(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_capture", lambda *a, **k: CAPTURED)
    monkeypatch.setattr(cli.service, "sync", lambda *a, **k: {"weekCards": []})
    assert cli.main(["--agent", "sync", "--week-start", "2026-08-17"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["_owa"]["tool"] == "owa-swodp"
    assert payload["data"] == {"weekCards": []}


def test_read_commands_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_capture", lambda *a, **k: CAPTURED)
    monkeypatch.setattr(cli.service, "week_cards", lambda *a, **k: [{"card": 1}])
    monkeypatch.setattr(cli.service, "history", lambda *a, **k: [{"history": 1}])
    monkeypatch.setattr(cli.service, "allocations", lambda *a, **k: [{"allocation": 1}])
    monkeypatch.setattr(cli.service, "categories", lambda *a, **k: {"Admin": "admin"})
    monkeypatch.setattr(cli.service, "task_lookup", lambda *a, **k: {"sys_id": "task"})
    commands = [
        ["cards", "--week-start", "2026-08-17"],
        ["history"],
        ["allocations", "--since", "2026-05-01"],
        ["categories"],
        ["task", "TABC123"],
    ]
    for args in commands:
        assert cli.main(args) == 0
        assert json.loads(capsys.readouterr().out) is not None


def test_task_missing_exits_not_found(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_capture", lambda *a, **k: CAPTURED)
    monkeypatch.setattr(cli.service, "task_lookup", lambda *a, **k: None)
    assert cli.main(["task", "TABC123"]) == int(ExitCode.NOT_FOUND)
    assert "not found" in capsys.readouterr().err


def test_write_loads_file_requires_confirmation_and_dispatches(tmp_path, monkeypatch, capsys):
    path = tmp_path / "rows.json"
    path.write_text(
        json.dumps([{"category": "admin", "days": [1, 0, 0, 0, 0, 0, 0], "description": "a"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_capture", lambda *a, **k: CAPTURED)
    monkeypatch.setattr(
        cli.service,
        "write_week",
        lambda *a, **k: [{"taskNumber": "category:admin", "action": "updated"}],
    )
    result = cli.main(
        ["write", "--instance", "uat", "--week-start", "2026-08-17", "--file", str(path), "--confirm"]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_help_version_schema_and_usage(capsys):
    assert cli.main(["--help"]) == 0
    assert "owa-swodp" in capsys.readouterr().out
    assert cli.main(["--version"]) == 0
    assert "owa-swodp" in capsys.readouterr().out
    assert cli.main(["schema", "write"]) == 0
    assert json.loads(capsys.readouterr().out)["tool"] == "owa-swodp"
    assert cli.main(["--err-json", "unknown"]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "USAGE"


def test_setup_and_reseed_choose_visibility(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "_capture",
        lambda instance, debug, visible=False: calls.append(visible) or CAPTURED,
    )
    assert cli.main(["setup"]) == 0
    capsys.readouterr()
    assert cli.main(["reseed"]) == 0
    assert calls == [True, False]


def test_status_without_profile_returns_auth_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli.session_mod, "profile_dir", lambda instance: tmp_path / "missing")
    assert cli.main(["--err-json", "status"]) == 11
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "AUTH_EXPIRED"


@pytest.mark.parametrize(
    "argv, message",
    [
        (["cards"], "--week-start is required"),
        (["cards", "--week-start", "2026-08-17", "--range-weeks", "x"], "integer"),
        (["history", "--bad"], "Unknown flag"),
        (["task"], "task number is required"),
        (["task", "TABC123", "extra"], "Unknown argument"),
        (["write", "--file", "x", "--confirm"], "--week-start is required"),
    ],
)
def test_usage_errors_are_structured(argv, message, capsys):
    assert cli.main(["--err-json", *argv]) == 2
    assert message in json.loads(capsys.readouterr().err)["error"]["message"]


def test_load_rows_reports_file_and_json_errors(tmp_path):
    with pytest.raises(Exception, match="could not read"):
        cli._load_rows(str(tmp_path / "missing"))
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    with pytest.raises(Exception, match="not valid JSON"):
        cli._load_rows(str(bad))


def test_card_commands_require_sys_id_and_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_capture", lambda *a, **k: CAPTURED)
    monkeypatch.setattr(
        cli.service, "delete_card", lambda *a, **k: {"action": "deleted", "sys_id": "x"}
    )
    monkeypatch.setattr(
        cli.service,
        "submit_card",
        lambda *a, **k: {"action": "submitted", "sys_id": "x", "state": "Submitted"},
    )
    monkeypatch.setattr(
        cli.service,
        "recall_card",
        lambda *a, **k: {"action": "recalled", "sys_id": "x", "state": "Recalled"},
    )
    for args in (
        ["delete", "x", "--confirm"],
        ["submit", "--sys-id", "x", "--confirm"],
        ["recall", "x", "--reason", "Correction", "--confirm"],
    ):
        assert cli.main(args) == 0
        assert json.loads(capsys.readouterr().out)["ok"] is True

    for command in ("submit", "recall", "delete"):
        assert cli.main([command, "--confirm"]) == int(ExitCode.USAGE)
        assert "sys id is required" in capsys.readouterr().err


def test_recall_requires_reason_before_capture(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "_capture", lambda *a, **k: pytest.fail("capture must not run")
    )
    assert cli.main(["recall", "x", "--confirm"]) == int(ExitCode.USAGE)
    assert "reason" in capsys.readouterr().err


def test_submit_conflicts_when_state_did_not_move(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_capture", lambda *a, **k: CAPTURED)
    monkeypatch.setattr(
        cli.service,
        "submit_card",
        lambda *a, **k: {"action": "submitted", "sys_id": "x", "detail": "state is Pending"},
    )
    assert cli.main(["submit", "x", "--confirm"]) == int(ExitCode.CONFLICT)
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_recall_conflicts_when_state_did_not_move(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_capture", lambda *a, **k: CAPTURED)
    monkeypatch.setattr(
        cli.service,
        "recall_card",
        lambda *a, **k: {"action": "recalled", "sys_id": "x", "detail": "state is Submitted"},
    )
    assert cli.main(["recall", "x", "--reason", "Correction", "--confirm"]) == int(
        ExitCode.CONFLICT
    )
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_card_commands_require_confirmation(monkeypatch):
    monkeypatch.setattr(cli.tty_mod, "confirm", lambda *a, **k: False)
    assert cli.main(["delete", "x"]) == int(ExitCode.USAGE)
