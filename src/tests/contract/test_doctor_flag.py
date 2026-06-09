"""Top-level --doctor flag on every owa-tools binary.

Each binary's main() goes through owa_core.modes.run_with_output_modes,
which intercepts --doctor before the legacy dispatcher. This contract
test exercises the actual entry points to pin the schema that
downstream doctor consumers fan out over.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from owa_core.registry import CONSUMER_TOOLS

# Each entry is (package_module, expected_tool_name). Derived from the
# canonical registry (plus the umbrella) so a newly added tool is
# automatically covered - this list previously drifted and omitted
# owa-todo. Use the package __main__ (python -m owa_cal), not the cli
# submodule, so the binary's own entry-point setup runs.
_BINARIES = [("owa", "owa")] + [
  (tool.replace("-", "_"), tool) for tool in CONSUMER_TOOLS
]


def _run(module: str, *args):
  return subprocess.run(
    [sys.executable, "-m", module, *args],
    capture_output=True, text=True,
  )


@pytest.mark.parametrize("module, tool", _BINARIES)
def test_doctor_json_shape(module, tool):
  result = _run(module, "--doctor", "--json")
  payload = json.loads(result.stdout.strip())
  assert payload["tool"] == tool
  assert "version" in payload
  assert isinstance(payload["findings"], list)
  # Reserved-key contract.
  assert "ok" not in payload


@pytest.mark.parametrize("module, tool", _BINARIES)
def test_doctor_human_default(module, tool):
  result = _run(module, "--doctor")
  assert f"{tool} doctor" in result.stdout


@pytest.mark.parametrize("module, tool", _BINARIES)
def test_doctor_redaction_sentinel(module, tool):
  result = _run(module, "--doctor", "--json")
  ids = [f["id"] for f in json.loads(result.stdout.strip())["findings"]]
  assert "redact_sentinel_leak" not in ids
  assert "redact_unavailable" not in ids


@pytest.mark.parametrize("module, tool", _BINARIES)
def test_doctor_exit_code_well_defined(module, tool):
  result = _run(module, "--doctor", "--json")
  # Either 0 (clean) or 1 (user-fixable). Should not be a crash.
  assert result.returncode in (0, 1)


def test_doctor_flag_in_value_position_is_not_intercepted():
  result = _run("owa_graph", "GET", "/me", "--header", "--doctor")
  assert "doctor" not in result.stdout
  assert "--header expects K=V" in result.stderr
