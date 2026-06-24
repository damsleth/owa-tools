"""Tests for the umbrella `owa` dispatcher."""
from __future__ import annotations

import json
import subprocess
import types

from owa import cli


def test_main_no_args_shows_help(capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "Tool dispatch" in out
    assert "Available tools:" in out and "cal" in out


def test_main_unknown_command_errors(capsys):
    assert cli.main(["missing"]) == 2
    assert "unknown command: missing" in capsys.readouterr().err


def test_cmd_version(capsys):
    assert cli.cmd_version([]) == 0
    assert capsys.readouterr().out.startswith("owa ")


def test_cmd_list_reports_installed_and_missing(monkeypatch, capsys):
    monkeypatch.setattr(cli, "CONSUMERS", ("owa-cal", "owa-mail"))
    monkeypatch.setattr(cli, "_which", lambda name: f"/bin/{name}" if name == "owa-cal" else None)
    monkeypatch.setattr(cli, "_version_of", lambda name: f"{name} 1.2.3")

    assert cli.cmd_list([]) == 0

    rows = json.loads(capsys.readouterr().out)
    assert rows == [
        {
            "tool": "owa-cal",
            "installed": True,
            "path": "/bin/owa-cal",
            "version": "owa-cal 1.2.3",
        },
        {
            "tool": "owa-mail",
            "installed": False,
            "path": None,
            "version": None,
        },
    ]


def test_cmd_list_pretty_renders_table(monkeypatch, capsys):
    monkeypatch.setattr(cli, "CONSUMERS", ("owa-cal", "owa-mail"))
    monkeypatch.setattr(cli, "_which", lambda name: f"/bin/{name}" if name == "owa-cal" else None)
    monkeypatch.setattr(cli, "_version_of", lambda name: f"{name} 1.2.3")

    assert cli.cmd_list(["--pretty"]) == 0

    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert lines[0].split() == ["tool", "state", "version", "path"]
    assert "owa-cal" in lines[1] and "ok" in lines[1] and "/bin/owa-cal" in lines[1]
    assert "owa-mail" in lines[2] and "missing" in lines[2]


def test_cmd_list_unknown_flag_errors(capsys):
    assert cli.cmd_list(["--bogus"]) == 2
    assert "unknown flag" in capsys.readouterr().err


def test_version_of_prefers_version_output(monkeypatch):
    monkeypatch.setattr(cli, "_which", lambda name: f"/bin/{name}")

    def fake_run(args, **kwargs):
        assert args == ["/bin/owa-cal", "--version"]
        assert kwargs["timeout"] == 5
        return subprocess.CompletedProcess(args, 0, stdout="owa-cal 9.9\n", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli._version_of("owa-cal") == "owa-cal 9.9"


def test_version_of_falls_back_to_help(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_which", lambda name: f"/bin/{name}")

    def fake_run(args, **kwargs):
        del kwargs
        calls.append(args[-1])
        if args[-1] == "--version":
            return subprocess.CompletedProcess(args, 2, stdout="", stderr="unknown command\n")
        return subprocess.CompletedProcess(args, 0, stdout="Usage: owa-mail\nmore\n", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli._version_of("owa-mail") == "Usage: owa-mail"
    assert calls == ["--version", "--help"]


def test_version_of_returns_none_when_missing_or_failing(monkeypatch):
    monkeypatch.setattr(cli, "_which", lambda name: None)
    assert cli._version_of("owa-cal") is None

    monkeypatch.setattr(cli, "_which", lambda name: f"/bin/{name}")

    def fail_run(args, **kwargs):
        del args, kwargs
        raise OSError("boom")

    monkeypatch.setattr(cli.subprocess, "run", fail_run)
    assert cli._version_of("owa-cal") is None


def _fake_tool_module(monkeypatch, expected_pkg, seen, rc=0):
    """Stub importlib so cmd_dispatch resolves a fake tool CLI whose
    main() records the argv it was handed and returns `rc`."""
    def fake_main(argv):
        seen["argv"] = argv
        return rc

    module = types.SimpleNamespace(main=fake_main)

    def fake_import(name):
        assert name == f"{expected_pkg}.cli", name
        return module

    monkeypatch.setattr(cli.importlib, "import_module", fake_import)


def test_dispatch_forwards_argv_to_tool_main(monkeypatch):
    seen = {}
    _fake_tool_module(monkeypatch, "owa_cal", seen)
    assert cli.main(["cal", "events", "--week", "16"]) == 0
    assert seen["argv"] == ["events", "--week", "16"]


def test_dispatch_accepts_binary_form_and_propagates_exit_code(monkeypatch):
    seen = {}
    _fake_tool_module(monkeypatch, "owa_mail", seen, rc=11)
    assert cli.main(["owa-mail", "messages"]) == 11
    assert seen["argv"] == ["messages"]


def test_doctor_dispatches_in_process(monkeypatch):
    seen = {}
    _fake_tool_module(monkeypatch, "owa_doctor", seen, rc=7)
    # No `probe` is inserted: owa-doctor defaults to probe on its own.
    assert cli.main(["doctor", "--no-tokens"]) == 7
    assert seen["argv"] == ["--no-tokens"]


def test_meta_command_takes_precedence_over_dispatch(monkeypatch, capsys):
    # `version` is a meta command, never dispatched to a tool.
    def boom(name):
        raise AssertionError(f"should not import {name}")

    monkeypatch.setattr(cli.importlib, "import_module", boom)
    assert cli.main(["version"]) == 0
    assert capsys.readouterr().out.startswith("owa ")


def test_cmd_schema_requires_tool_value(capsys):
    assert cli.cmd_schema(["--tool"]) == 2
    assert "--tool requires a value" in capsys.readouterr().err


def test_cmd_schema_aggregates_schema_outcomes(monkeypatch, capsys):
    # Use proper "owa-<short>" names so TOOL_PACKAGES lookup succeeds.
    monkeypatch.setattr(cli, "CONSUMERS", ("owa-ok", "owa-missing", "owa-noschema"))
    monkeypatch.setattr(cli, "TOOL_PACKAGES", {
        "ok": "owa_ok",
        "missing": "owa_missing",
        "noschema": "owa_noschema",
    })

    ok_module = types.SimpleNamespace(COMMAND_SCHEMA=[{"name": "events"}])
    noschema_module = types.SimpleNamespace()  # no COMMAND_SCHEMA attr

    def fake_import(name):
        if name == "owa_ok.cli":
            return ok_module
        if name == "owa_missing.cli":
            raise ImportError("not installed")
        if name == "owa_noschema.cli":
            return noschema_module
        raise ImportError(name)

    monkeypatch.setattr(cli.importlib, "import_module", fake_import)
    assert cli.cmd_schema([]) == 0

    rows = json.loads(capsys.readouterr().out)
    # owa-ok: imported successfully, has COMMAND_SCHEMA
    assert rows[0]["tool"] == "owa-ok"
    assert rows[0]["installed"] is True
    assert rows[0]["schema_supported"] is True
    assert rows[0]["schema"]["commands"] == [{"name": "events"}]
    # owa-missing: ImportError -> installed=False
    assert rows[1] == {"tool": "owa-missing", "installed": False}
    # owa-noschema: imported but no COMMAND_SCHEMA attr
    assert rows[2]["tool"] == "owa-noschema"
    assert rows[2]["installed"] is True
    assert rows[2]["schema_supported"] is False


def test_cmd_schema_tool_filters_consumers(monkeypatch, capsys):
    monkeypatch.setattr(cli, "CONSUMERS", ("owa-a", "owa-b"))
    monkeypatch.setattr(cli, "TOOL_PACKAGES", {"a": "owa_a", "b": "owa_b"})
    # owa-b has no COMMAND_SCHEMA
    monkeypatch.setattr(
        cli.importlib,
        "import_module",
        lambda name: types.SimpleNamespace(),
    )

    assert cli.cmd_schema(["--tool", "owa-b"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [row["tool"] for row in rows] == ["owa-b"]
    assert rows[0]["schema_supported"] is False


# ── run_with_output_modes routing (task 1) ───────────────────────────────────

def test_list_agent_emits_envelope(monkeypatch, capsys):
    """--agent on `list` must produce {"_owa": ..., "data": [...]} envelope."""
    monkeypatch.setattr(cli, "CONSUMERS", ("owa-cal",))
    monkeypatch.setattr(cli, "_which", lambda name: None)
    monkeypatch.setattr(cli, "_version_of", lambda name: None)

    rc = cli.main(["--agent", "list"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "_owa" in payload
    assert payload["_owa"]["tool"] == "owa"
    assert isinstance(payload["data"], list)
    assert payload["data"][0]["tool"] == "owa-cal"


def test_meta_dispatch_unknown_command_errors(capsys):
    """_meta_dispatch must write the error message and return 2."""
    rc = cli._meta_dispatch(["no-such-command"])
    assert rc == 2
    assert "unknown command: no-such-command" in capsys.readouterr().err


# ── in-process schema aggregation (task 2) ───────────────────────────────────

def test_cmd_schema_uses_inprocess_import_not_subprocess(monkeypatch, capsys):
    """cmd_schema must NOT call subprocess.run; it imports COMMAND_SCHEMA."""
    monkeypatch.setattr(cli, "CONSUMERS", ("owa-cal",))
    monkeypatch.setattr(cli, "TOOL_PACKAGES", {"cal": "owa_cal_stub"})

    cal_module = types.SimpleNamespace(COMMAND_SCHEMA=[{"name": "events"}])
    monkeypatch.setattr(cli.importlib, "import_module", lambda name: cal_module)

    def boom(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called by cmd_schema")

    monkeypatch.setattr(cli.subprocess, "run", boom)

    assert cli.cmd_schema([]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["schema_supported"] is True
    # schema_for wraps COMMAND_SCHEMA under the canonical schema envelope
    assert rows[0]["schema"]["tool"] == "owa-cal"
    assert rows[0]["schema"]["commands"] == [{"name": "events"}]
