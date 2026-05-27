"""owa-tools binding to the shared hugr CLI contract.

The wire contract (action/error envelopes, NDJSON streaming, the
doctor payload shape, the 0-5 exit-code taxonomy) lives in the
``hugr-conventions`` package - the executable form of CONVENTIONS.md
in the hugr repo. This module binds it to the owa-tools suite version
and owa's own redactor, and keeps the owa-specific ``--doctor``
default payload (the redaction-sentinel smoke test). All nine
``owa-*`` binaries (owa, owa-cal, owa-mail, owa-graph, owa-doctor,
owa-people, owa-sched, owa-drive, owa-todo) import the contract
surface from here, so it is enforced once.

Reuses ``owa_core.secrets.redact()`` as the redaction primitive
(richer than the suite floor: it also scrubs attachment paths), so
``conventions.redact is owa_core.secrets.redact``.

The ``EXIT_*`` constants here use the hugr 0-5 ``--doctor`` taxonomy.
That range is distinct from the main owa-tools exit-code taxonomy
(0/2/10-15/20 in ``owa_core.errors.ExitCode``) and applies only to the
``--doctor`` surface. AGENTS.md documents the carve-out. Tools that
need the main taxonomy raise an ``OwaError`` subclass instead.

See https://github.com/damsleth/hugr/blob/main/CONVENTIONS.md.
"""

from __future__ import annotations

from typing import Any

import hugr_conventions as _hc
from hugr_conventions import (  # re-export: identical wire shapes
    EXIT_AUTH,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_PARTIAL,
    EXIT_TRANSIENT,
    EXIT_USER_ERROR,
    DoctorFinding,
    emit_action,
    emit_data_error,
)

from owa_core.secrets import redact  # re-export: owa's own richer redactor
from owa_core.version import suite_version

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


def _version() -> str:
    """Suite semver. Envelope/doctor consumers expect a bare version
    string, not the binary-prefixed form."""
    try:
        return suite_version()
    except Exception:
        return "0.0.0"


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
    return _hc.action_envelope(
        tool=tool,
        version=_version,
        command=command,
        ok=ok,
        stats=stats,
        warnings=warnings,
        error=error,
        duration_ms=duration_ms,
    )


def data_error(
    *,
    tool: str,
    command: str,
    code: str,
    message: str,
    hint: str | None = None,
) -> dict:
    return _hc.data_error(
        tool=tool,
        version=_version,
        command=command,
        code=code,
        message=message,
        hint=hint,
    )


def DoctorPayload(**kwargs: Any) -> _hc.DoctorPayload:  # noqa: N802 - preserves call site
    """owa-bound :class:`hugr_conventions.DoctorPayload`.

    Defaults ``version`` to the suite version; ``tool`` is supplied by
    the caller (each binary passes its own name).
    """
    kwargs.setdefault("version", _version)
    return _hc.DoctorPayload(**kwargs)


def _run_default_doctor(tool: str) -> _hc.DoctorPayload:
    """Default per-binary doctor: redaction-sentinel smoke test.

    Each binary can extend by passing ``extra_findings`` to
    :func:`emit_doctor`. For hugr's fan-out only the shape is
    contractual.
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
    """Emit the standard ``--doctor`` surface for a given binary.

    ``extra_findings`` lets a binary append checks beyond the defaults
    (e.g. owa-mail can probe a mailbox, owa-cal can probe calendar
    access).
    """
    payload = _run_default_doctor(tool)
    if extra_findings:
        payload.findings.extend(extra_findings)
    return _hc.emit_doctor(payload, as_json=as_json)
