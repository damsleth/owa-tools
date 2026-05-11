"""Direct command tests for owa-doctor."""

import json

import pytest

from owa_doctor import cli


def _stub_probe(monkeypatch, *, token_minutes=60, installed=True):
    monkeypatch.setattr(cli.probe_mod, "probe_piggy", lambda: {
        "installed": installed,
        "version": "0.8.0" if installed else None,
        "path": "/bin/owa-piggy" if installed else None,
    })
    monkeypatch.setattr(cli.probe_mod, "probe_siblings", lambda: [
        {"name": "owa-cal", "installed": True, "version": "1.0"},
    ])
    monkeypatch.setattr(cli.probe_mod, "list_piggy_profiles", lambda: (["work", "home"], "work"))

    def fake_token(alias, audience="graph"):
        return {
            "alias": alias,
            "audience": audience,
            "token_ok": token_minutes > 0,
            "minutes_remaining": token_minutes,
            "error": None if token_minutes > 0 else "expired",
        }

    monkeypatch.setattr(cli.probe_mod, "probe_profile_token", fake_token)

    def classify(finding):
        if not finding["token_ok"]:
            return "fail"
        if finding["minutes_remaining"] < 10:
            return "warn"
        return "ok"

    monkeypatch.setattr(cli.probe_mod, "classify_finding", classify)


def test_parse_args_all_options():
    assert cli._parse_args([
        "--profile",
        "work",
        "--audience",
        "outlook",
        "--no-tokens",
        "--pretty",
        "--debug",
    ]) == ("work", "outlook", True, True, True)

    with pytest.raises(cli.UsageError, match="--profile requires"):
        cli._parse_args(["--profile"])
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli._parse_args(["--bogus"])


def test_main_schema_pretty_warn_and_filter(monkeypatch, capsys):
    _stub_probe(monkeypatch, token_minutes=5)

    assert cli._main(["schema"]) == 0
    assert json.loads(capsys.readouterr().out)["tool"] == "owa-doctor"

    assert cli._main(["probe", "--profile", "work", "--audience", "outlook", "--pretty", "--debug"]) == 1
    captured = capsys.readouterr()
    assert "owa-piggy: ok" in captured.out
    assert "Summary: 0 ok, 1 warn, 0 fail" in captured.out
    assert "DEBUG: probing token for work" in captured.err


def test_main_json_failures_and_unknown_profile(monkeypatch, capsys):
    _stub_probe(monkeypatch, token_minutes=0)
    assert cli._main([]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["fail"] == 2

    with pytest.raises(cli.UsageError, match="not found"):
        cli.build_report(profile_filter="missing")

    _stub_probe(monkeypatch, installed=False)
    assert cli._main(["--no-tokens"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["profiles"] == []

    assert cli._main(["frobnicate"]) == 2
    assert "Unknown command" in capsys.readouterr().err


def test_exit_code_for_reports():
    assert cli._exit_code_for({"owa_piggy": {"installed": False}, "summary": {}}) == 2
    assert cli._exit_code_for({"owa_piggy": {"installed": True}, "summary": {"fail": 1}}) == 2
    assert cli._exit_code_for({"owa_piggy": {"installed": True}, "summary": {"warn": 1}}) == 1
    assert cli._exit_code_for({"owa_piggy": {"installed": True}, "summary": {"ok": 1}}) == 0
