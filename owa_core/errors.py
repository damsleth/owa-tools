"""Shared error taxonomy for owa-tools CLIs.

Keep this module small and stdlib-only. Tool-specific command handlers can
raise these errors directly, while legacy command paths can still emit plain
stderr and return integers until they are migrated.
"""
import sys
from enum import IntEnum

from .secrets import redact


class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    NETWORK = 10
    AUTH_EXPIRED = 11
    SCOPE_INSUFFICIENT = 12
    NOT_FOUND = 13
    RATE_LIMITED = 14
    CONFLICT = 15
    INTERNAL = 20


class OwaError(Exception):
    """Base class for expected CLI failures."""

    exit_code = ExitCode.INTERNAL

    def __init__(self, message, *, remediation=None, cause=None):
        super().__init__(message)
        self.message = message
        self.remediation = remediation
        self.cause = cause


class UsageError(OwaError):
    exit_code = ExitCode.USAGE


class NetworkError(OwaError):
    exit_code = ExitCode.NETWORK


class AuthExpiredError(OwaError):
    exit_code = ExitCode.AUTH_EXPIRED


class ScopeInsufficientError(OwaError):
    exit_code = ExitCode.SCOPE_INSUFFICIENT


class NotFoundError(OwaError):
    exit_code = ExitCode.NOT_FOUND


class RateLimitedError(OwaError):
    exit_code = ExitCode.RATE_LIMITED


class ConflictError(OwaError):
    exit_code = ExitCode.CONFLICT


class InternalError(OwaError):
    exit_code = ExitCode.INTERNAL


def emit_error(error, *, stream=None):
    """Print one human-readable error to stderr and return its exit code."""
    stream = stream or sys.stderr
    print(f'ERROR: {redact(error.message)}', file=stream)
    if error.remediation:
        print(f'hint: {redact(error.remediation)}', file=stream)
    return int(error.exit_code)
