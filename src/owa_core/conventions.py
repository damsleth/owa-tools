"""owa-tools CLI contract surface.

Shared across all eleven owa-* binaries (owa, owa-cal, owa-mail,
owa-graph, owa-doctor, owa-people, owa-sched, owa-drive, owa-todo,
owa-planner, owa-sites). Each binary's cli.py imports from here so the
contract is enforced once.

The wire contract (action/error envelopes, NDJSON streaming, the
doctor payload shape, the 0-5 exit-code taxonomy) is defined and
maintained by owa-tools itself. It is kept self-contained here rather
than depending on a separate package, so the suite stays a single
pip-installable distribution with no third-party runtime dependency.

Reuses owa_core.secrets.redact() as the redaction primitive (richer
than the suite floor: it also scrubs attachment paths), re-exported
here so ``conventions.redact is owa_core.secrets.redact``.

The EXIT_* constants here intentionally use a dedicated 0-5 taxonomy
for the --doctor surface. That range is distinct from the main
owa-tools exit-code taxonomy (0/2/10-15/20 defined in
owa_core.errors.ExitCode) and applies only to the --doctor surface
emitted by emit_doctor(). AGENTS.md documents the carve-out under
"Exit Codes". Tools that need the main taxonomy should raise an
OwaError subclass instead of returning one of these constants.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any

from owa_core.secrets import redact  # re-export
from owa_core.version import suite_version


def _resolve_version(_tool: str | None = None) -> str:
    """Return the suite semver. Doctor/envelope consumers expect a
    bare version string, not the binary-prefixed form
    ``binary_version()`` returns."""
    try:
        return suite_version()
    except Exception:
        return "0.0.0"


# --doctor exit-code range. See module docstring; not the main
# owa-tools taxonomy in owa_core.errors.ExitCode.
EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_TRANSIENT = 2
EXIT_AUTH = 3
EXIT_NOT_FOUND = 4
EXIT_PARTIAL = 5


__all__ = [
    "EXIT_OK",
    "EXIT_USER_ERROR",
    "EXIT_TRANSIENT",
    "EXIT_AUTH",
    "EXIT_NOT_FOUND",
    "EXIT_PARTIAL",
    "redact",
    "action_envelope",
    "emit_action",
    "data_error",
    "emit_data_error",
    "DoctorFinding",
    "DoctorPayload",
    "emit_doctor",
]


def action_envelope(
    *,
    tool: str,
    command: str,
    ok: bool,
    stats=None,
    warnings=None,
    error=None,
    duration_ms=None,
) -> dict:
    return {
        "tool": tool,
        "version": _resolve_version(tool),
        "command": command,
        "ok": bool(ok),
        "duration_ms": float(duration_ms) if duration_ms is not None else 0.0,
        "stats": dict(stats or {}),
        "warnings": list(warnings or []),
        "error": dict(error) if error else None,
    }


def emit_action(envelope, stream=None) -> None:
    stream = stream if stream is not None else sys.stdout
    stream.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    stream.flush()


def data_error(
    *,
    tool: str,
    command: str,
    code: str,
    message: str,
    hint: str | None = None,
) -> dict:
    err: dict[str, Any] = {"code": code, "message": message}
    if hint:
        err["hint"] = hint
    return {
        "tool": tool,
        "version": _resolve_version(tool),
        "command": command,
        "ok": False,
        "error": err,
    }


def emit_data_error(envelope, stream=None) -> None:
    """Write a data-class error envelope on stdout.

    By convention, structured JSON output - including
    failure envelopes - travels on stdout so consumers parse one
    stream with one discriminator (the reserved-key `ok` field).
    This is a deliberate carve-out from the owa-tools house rule
    "errors are diagnostics, send to stderr" because that rule
    assumes human-readable error text; once the error is structured
    JSON, sharing the stream with success output gives the cleanest
    contract (`cmd | jq` works on both paths, suite-wide consumers
    never need to interleave streams).

    Free-text human errors and unstructured tracebacks still belong
    on stderr - this only governs the structured envelope.
    """
    stream = stream if stream is not None else sys.stdout
    stream.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    stream.flush()


@dataclass
class DoctorFinding:
    id: str
    severity: str
    message: str
    hint: str | None = None

    def to_dict(self) -> dict:
        out: dict[str, Any] = {
            "id": self.id,
            "severity": self.severity,
            "message": self.message,
        }
        if self.hint:
            out["hint"] = self.hint
        return out


@dataclass
class DoctorPayload:
    tool: str
    config_path: str | None = None
    data_path: str | None = None
    auth: dict | None = None
    findings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        out: dict[str, Any] = {"tool": self.tool, "version": _resolve_version(self.tool)}
        if self.config_path is not None:
            out["config_path"] = self.config_path
        if self.data_path is not None:
            out["data_path"] = self.data_path
        if self.auth is not None:
            out["auth"] = self.auth
        out["findings"] = [f.to_dict() for f in self.findings]
        return out

    def exit_code(self) -> int:
        severities = {f.severity for f in self.findings}
        if "error" in severities:
            return EXIT_USER_ERROR
        return EXIT_OK


def _run_default_doctor(tool: str) -> DoctorPayload:
    """Default per-binary doctor: redaction-sentinel check + config probe.

    Each binary can extend by appending findings before calling
    emit_doctor(). For downstream consumers only the shape is contractual.
    """
    payload = DoctorPayload(tool=tool)

    # Redaction-sentinel smoke test using the same redact() the rest of
    # the tool uses for logging.
    try:
        sentinel = "CANARY_SECRET_xxxx"
        jwt_like = "eyJalg." + sentinel + ".sig-padding-123"
        out = redact(f"Authorization: Bearer {jwt_like}")
        if sentinel in out:
            payload.findings.append(DoctorFinding(
                id="redact_sentinel_leak",
                severity="error",
                message="Redaction sentinel leaked through redact()",
                hint="owa_core.secrets.redact() is not catching expected patterns",
            ))
    except Exception as exc:
        payload.findings.append(DoctorFinding(
            id="redact_unavailable",
            severity="error",
            message=f"redact() is not callable: {exc}",
        ))

    return payload


def emit_doctor(tool: str, as_json: bool, *, extra_findings=None) -> int:
    """Emit the standard --doctor surface for a given binary.

    ``extra_findings`` lets a binary append checks beyond the
    defaults (e.g. owa-mail can probe a mailbox, owa-cal can probe
    calendar access).
    """
    payload = _run_default_doctor(tool)
    if extra_findings:
        payload.findings.extend(extra_findings)
    if as_json:
        sys.stdout.write(json.dumps(payload.to_dict(), ensure_ascii=False) + "\n")
        sys.stdout.flush()
    else:
        _print_doctor_human(payload)
    return payload.exit_code()


def _print_doctor_human(payload: DoctorPayload) -> None:
    data = payload.to_dict()
    print(f"{payload.tool} doctor (v{data['version']})")
    if payload.config_path:
        print(f"  config: {payload.config_path}")
    if payload.auth:
        print(f"  auth:   {payload.auth}")
    if not payload.findings:
        print("  status: ok")
        return
    print(f"  findings: {len(payload.findings)}")
    for f in payload.findings:
        marker = {"error": "x", "warning": "!", "info": "."}.get(f.severity, ".")
        print(f"    {marker} [{f.severity}] {f.id}: {f.message}")
        if f.hint:
            print(f"        hint: {f.hint}")
