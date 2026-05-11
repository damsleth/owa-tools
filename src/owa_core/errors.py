"""Shared error taxonomy for owa-tools CLIs.

Keep this module small and stdlib-only. Tool-specific command handlers can
raise these errors directly, while legacy command paths can still emit plain
stderr and return integers until they are migrated.
"""
import json
import os
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


def _env_truthy(name):
    return os.environ.get(name, '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _error_code(error):
    name = type(error).__name__
    if name.endswith('Error'):
        name = name[:-5]
    out = []
    for idx, char in enumerate(name):
        if char.isupper() and idx:
            out.append('_')
        out.append(char.upper())
    return ''.join(out) or 'ERROR'


def emit_error(error, *, stream=None, tool=None, command=None, err_json=None):
    """Print one error to stderr and return its exit code."""
    stream = stream or sys.stderr
    if err_json is None:
        err_json = _env_truthy('OWA_ERR_JSON') or _env_truthy('OWA_ERR_JSON_ACTIVE')
    if err_json:
        payload = {
            'error': {
                'code': _error_code(error),
                'message': redact(error.message),
                'exit_code': int(error.exit_code),
            }
        }
        tool = tool or os.environ.get('OWA_TOOL')
        command = command or os.environ.get('OWA_COMMAND')
        if error.remediation:
            payload['error']['hint'] = redact(error.remediation)
        if tool:
            payload['error']['tool'] = tool
        if command:
            payload['error']['command'] = command
        json.dump(payload, stream, ensure_ascii=False, separators=(',', ':'))
        stream.write('\n')
        return int(error.exit_code)

    print(f'ERROR: {redact(error.message)}', file=stream)
    if error.remediation:
        print(f'hint: {redact(error.remediation)}', file=stream)
    return int(error.exit_code)


def emit_message(message, *, stream=None, exit_code=ExitCode.USAGE):
    error = UsageError(message)
    error.exit_code = exit_code
    return emit_error(error, stream=stream)
