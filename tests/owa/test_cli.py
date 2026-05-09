"""Tests for the umbrella `owa` dispatcher."""
from __future__ import annotations

import json
import subprocess

from owa import cli


def test_main_no_args_shows_help(capsys):
    assert cli.main([]) == 0
    assert "Subcommands:" in capsys.readouterr().out


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


def test_cmd_doctor_requires_installed_binary(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_which", lambda name: None)
    assert cli.cmd_doctor([]) == 13
    assert "owa-doctor not on PATH" in capsys.readouterr().err


def test_cmd_doctor_forwards_probe(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "_which", lambda name: "/bin/owa-doctor")

    def fake_call(args):
        seen["args"] = args
        return 7

    monkeypatch.setattr(cli.subprocess, "call", fake_call)
    assert cli.cmd_doctor(["--pretty"]) == 7
    assert seen["args"] == ["/bin/owa-doctor", "probe", "--pretty"]


def test_cmd_schema_requires_tool_value(capsys):
    assert cli.cmd_schema(["--tool"]) == 2
    assert "--tool requires a value" in capsys.readouterr().err


def test_cmd_schema_aggregates_schema_outcomes(monkeypatch, capsys):
    monkeypatch.setattr(cli, "CONSUMERS", ("ok", "missing", "bad-json", "timeout"))
    paths = {"ok": "/bin/ok", "bad-json": "/bin/bad-json", "timeout": "/bin/timeout"}
    monkeypatch.setattr(cli, "_which", lambda name: paths.get(name))

    def fake_run(args, **kwargs):
        assert args[1] == "schema"
        assert kwargs["capture_output"] is True
        if args[0] == "/bin/ok":
            return subprocess.CompletedProcess(args, 0, stdout='{"commands":[]}', stderr="")
        if args[0] == "/bin/bad-json":
            return subprocess.CompletedProcess(args, 0, stdout="not-json", stderr="")
        raise subprocess.TimeoutExpired(args, 5)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli.cmd_schema([]) == 0

    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["schema_supported"] is True
    assert rows[0]["schema"] == {"commands": []}
    assert rows[1] == {"tool": "missing", "installed": False}
    assert rows[2]["schema_supported"] is False
    assert "non-JSON" in rows[2]["error"]
    assert rows[3]["schema_supported"] is False


def test_cmd_schema_tool_filters_consumers(monkeypatch, capsys):
    monkeypatch.setattr(cli, "CONSUMERS", ("a", "b"))
    monkeypatch.setattr(cli, "_which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 1, stdout="", stderr=""),
    )

    assert cli.cmd_schema(["--tool", "b"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [row["tool"] for row in rows] == ["b"]
    assert rows[0]["schema_supported"] is False
