"""Tests for owa_core/conventions.py - the mnem CLI contract surface.

Reuses owa_core.secrets.redact() and adds the envelope + doctor
contract layers that mnem CONVENTIONS.md requires.
"""
from __future__ import annotations

import io
import json

from owa_core.conventions import (
  DoctorFinding,
  DoctorPayload,
  EXIT_OK,
  EXIT_PARTIAL,
  EXIT_USER_ERROR,
  action_envelope,
  data_error,
  emit_action,
  emit_data_error,
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


def test_action_envelope_shape():
  env = action_envelope(tool="owa-cal", command="create", ok=True, stats={"event_id": "x"})
  assert env["tool"] == "owa-cal"
  assert "version" in env
  assert env["command"] == "create"
  assert env["ok"] is True
  assert env["stats"]["event_id"] == "x"


def test_action_envelope_failure_carries_error():
  env = action_envelope(
    tool="owa-mail", command="send", ok=False,
    error={"code": "auth_expired", "message": "M365 token expired"},
  )
  assert env["ok"] is False
  assert env["error"]["code"] == "auth_expired"


def test_emit_action_one_line():
  buf = io.StringIO()
  emit_action(action_envelope(tool="owa-cal", command="x", ok=True), stream=buf)
  payload = json.loads(buf.getvalue())
  assert payload["command"] == "x"


def test_data_error_shape():
  err = data_error(tool="owa-cal", command="events", code="auth_expired", message="m", hint="setup")
  assert err["tool"] == "owa-cal"
  assert err["ok"] is False
  assert err["error"]["hint"] == "setup"


def test_emit_data_error_one_line():
  buf = io.StringIO()
  emit_data_error(data_error(tool="owa-cal", command="x", code="c", message="m"), stream=buf)
  assert json.loads(buf.getvalue())["ok"] is False


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
