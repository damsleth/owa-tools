"""Tests for owa_core/conventions.py - the owa-tools CLI contract surface.

Reuses owa_core.secrets.redact() and adds the envelope + doctor
contract layers that the owa-tools conventions require.
"""
from __future__ import annotations

import json

from owa_core.conventions import (
  EXIT_OK,
  EXIT_PARTIAL,
  EXIT_USER_ERROR,
  DoctorFinding,
  DoctorPayload,
  emit_doctor,
  redact,
)


def test_redact_is_owa_core_redact():
  """conventions.redact must be the same callable as owa_core.secrets.redact."""
  from owa_core.secrets import redact as _direct
  assert redact is _direct


def test_redaction_sentinel_does_not_leak():
  jwt = "eyJfake.payload-CANARY_SECRET_xxxx.padding1234"
  out = redact(f"Authorization: Bearer {jwt}")
  assert "CANARY_SECRET_xxxx" not in out


def test_doctor_payload_to_dict():
  d = DoctorPayload(
    tool="owa-graph",
    findings=[DoctorFinding(id="x", severity="warning", message="m")],
  ).to_dict()
  assert d["tool"] == "owa-graph"
  assert "version" in d
  assert d["findings"][0]["severity"] == "warning"
  # Reserved-key contract.
  assert "ok" not in d


def test_doctor_exit_codes():
  assert DoctorPayload(tool="owa-cal").exit_code() == EXIT_OK
  d = DoctorPayload(tool="owa-cal", findings=[DoctorFinding(id="x", severity="error", message="m")])
  assert d.exit_code() == EXIT_USER_ERROR


def test_exit_constants():
  assert EXIT_OK == 0
  assert EXIT_USER_ERROR == 1
  assert EXIT_PARTIAL == 5


def test_doctor_payload_optional_fields_in_dict():
  d = DoctorPayload(
    tool="owa-mail",
    config_path="/tmp/cfg",
    data_path="/tmp/data",
    auth={"profile": "globex"},
  ).to_dict()
  assert d["config_path"] == "/tmp/cfg"
  assert d["data_path"] == "/tmp/data"
  assert d["auth"] == {"profile": "globex"}


def test_emit_doctor_json_clean_run(capsys):
  rc = emit_doctor("owa-cal", as_json=True)
  out = capsys.readouterr().out
  payload = json.loads(out)
  assert rc == EXIT_OK
  assert payload["tool"] == "owa-cal"
  assert payload["findings"] == []


def test_emit_doctor_human_with_findings(capsys):
  rc = emit_doctor(
    "owa-cal",
    as_json=False,
    extra_findings=[
      DoctorFinding(id="warn1", severity="warning", message="check this", hint="try X"),
      DoctorFinding(id="err1", severity="error", message="broken"),
      DoctorFinding(id="info1", severity="info", message="fyi"),
    ],
  )
  out = capsys.readouterr().out
  assert rc == EXIT_USER_ERROR
  assert "owa-cal doctor" in out
  assert "findings: 3" in out
  assert "[warning] warn1" in out
  assert "hint: try X" in out
  assert "[error] err1" in out
  assert "[info] info1" in out


def test_emit_doctor_human_clean(capsys):
  rc = emit_doctor("owa-graph", as_json=False)
  out = capsys.readouterr().out
  assert rc == EXIT_OK
  assert "status: ok" in out


def test_emit_doctor_human_renders_config_and_auth(capsys, monkeypatch):
  # _run_default_doctor builds a fresh payload, so to exercise the
  # config_path/auth branches in _print_doctor_human we install a
  # fake doctor that returns a populated payload.
  from owa_core import conventions

  fake = DoctorPayload(
    tool="owa-mail",
    config_path="/tmp/cfg",
    auth={"profile": "globex"},
    findings=[DoctorFinding(id="x", severity="info", message="hi")],
  )
  monkeypatch.setattr(conventions, "_run_default_doctor", lambda _tool: fake)
  rc = conventions.emit_doctor("owa-mail", as_json=False)
  out = capsys.readouterr().out
  assert rc == EXIT_OK
  assert "config: /tmp/cfg" in out
  assert "auth:" in out
