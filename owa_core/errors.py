"""Exit-code taxonomy and structured-error envelope.

The taxonomy is the agent contract. Per-tool exceptions (e.g., owa-doctor's
0/1/2 Nagios codes) override at the command level only, never at the suite
level.

Public surface:
    ExitCode (IntEnum)
    OwaError (base)
    UsageError, NetworkError, AuthExpiredError, ScopeInsufficientError,
    NotFoundError, RateLimitedError, ConflictError, InternalError
    emit(err, *, tool, command, err_json=None, stream=None) -> int
"""
from __future__ import annotations

import json
import os
import sys
from enum import IntEnum
from typing import IO


class ExitCode(IntEnum):
    OK = 0
    USAGE = 2
    NETWORK = 10
    AUTH_EXPIRED = 11
    SCOPE_INSUFFICIENT = 12
    NOT_FOUND = 13
    RATE_LIMITED = 14
    CONFLICT = 15
    INTERNAL = 20


class OwaError(Exception):
    code: ExitCode = ExitCode.INTERNAL
    error_code: str = "INTERNAL"

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class UsageError(OwaError):
    code = ExitCode.USAGE
    error_code = "USAGE"


class NetworkError(OwaError):
    code = ExitCode.NETWORK
    error_code = "NETWORK"


class AuthExpiredError(OwaError):
    code = ExitCode.AUTH_EXPIRED
    error_code = "AUTH_EXPIRED"


class ScopeInsufficientError(OwaError):
    code = ExitCode.SCOPE_INSUFFICIENT
    error_code = "SCOPE_INSUFFICIENT"


class NotFoundError(OwaError):
    code = ExitCode.NOT_FOUND
    error_code = "NOT_FOUND"


class RateLimitedError(OwaError):
    code = ExitCode.RATE_LIMITED
    error_code = "RATE_LIMITED"


class ConflictError(OwaError):
    code = ExitCode.CONFLICT
    error_code = "CONFLICT"


class InternalError(OwaError):
    code = ExitCode.INTERNAL
    error_code = "INTERNAL"


def _err_json_enabled(explicit: bool | None) -> bool:
    # Truthy explicit always wins. Falsy/None falls back to the env var,
    # so `--err-json` can be set on the dispatcher without disabling the
    # OWA_ERR_JSON escape hatch when the flag was simply absent.
    if explicit:
        return True
    return os.environ.get("OWA_ERR_JSON", "").strip() in ("1", "true", "yes")


def emit(
    err: OwaError,
    *,
    tool: str,
    command: str,
    err_json: bool | None = None,
    stream: IO[str] | None = None,
) -> int:
    """Render the error to stderr and return its exit code.

    Default is a one-line human message: ``ERROR: <message>`` followed by
    an optional ``hint: <hint>`` line. With ``err_json=True`` (or
    ``OWA_ERR_JSON=1``), emits a structured envelope:

        {"error": {"code", "message", "hint", "tool", "command", "exit_code"}}
    """
    out = stream if stream is not None else sys.stderr
    if _err_json_enabled(err_json):
        envelope = {
            "error": {
                "code": err.error_code,
                "message": err.message,
                "hint": err.hint,
                "tool": tool,
                "command": command,
                "exit_code": int(err.code),
            }
        }
        out.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    else:
        out.write(f"ERROR: {err.message}\n")
        if err.hint:
            out.write(f"hint: {err.hint}\n")
    return int(err.code)
