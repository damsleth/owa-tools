"""Shared top-level CLI modes for agent and structured-error consumers."""
import contextlib
import io
import json
import os
import sys

from .errors import OwaError, UsageError, emit_error
from .schema import SCHEMA_VERSION
from .version import suite_version

_TRUTHY = {'1', 'true', 'yes', 'on'}


def env_truthy(name):
    return os.environ.get(name, '').strip().lower() in _TRUTHY


def split_mode_flags(argv):
    agent = env_truthy('OWA_AGENT')
    err_json = env_truthy('OWA_ERR_JSON')
    filtered = []
    for arg in argv:
        if arg == '--agent':
            agent = True
        elif arg == '--err-json':
            err_json = True
        else:
            filtered.append(arg)
    return agent, err_json, filtered


def command_name(argv):
    for arg in argv:
        if arg == '--':
            return ''
        if not arg.startswith('-'):
            return arg
    return ''


def envelope(tool, command, data):
    meta = {
        'suite': 'owa-tools',
        'tool': tool,
        'version': suite_version(),
        'schema_version': SCHEMA_VERSION,
    }
    if command:
        meta['command'] = command
    profile = os.environ.get('OWA_PROFILE', '').strip()
    if profile:
        meta['profile'] = profile
    return {'_owa': meta, 'data': data}


def is_doctor_invocation(argv):
    """Return True only for the top-level hugr --doctor surface.

    Command-specific arguments may legitimately contain the literal
    string ``--doctor`` as a value. Treat it as doctor mode only when
    the whole invocation is the doctor flag plus its output-mode flag.
    """
    return bool(argv) and '--doctor' in argv and all(
        arg in ('--doctor', '--json') for arg in argv
    )


@contextlib.contextmanager
def _mode_environment(tool, command, err_json):
    previous = {
        'OWA_TOOL': os.environ.get('OWA_TOOL'),
        'OWA_COMMAND': os.environ.get('OWA_COMMAND'),
        'OWA_ERR_JSON_ACTIVE': os.environ.get('OWA_ERR_JSON_ACTIVE'),
    }
    os.environ['OWA_TOOL'] = tool
    if command:
        os.environ['OWA_COMMAND'] = command
    else:
        os.environ.pop('OWA_COMMAND', None)
    if err_json:
        os.environ['OWA_ERR_JSON_ACTIVE'] = '1'
    else:
        os.environ.pop('OWA_ERR_JSON_ACTIVE', None)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_with_output_modes(tool, argv, dispatch, *, binary_stdout_commands=()):
    """Run a legacy CLI dispatcher with shared agent/error modes.

    `dispatch` receives argv with global mode flags removed and returns an
    integer exit code. In agent mode, successful JSON stdout is wrapped in a
    stable envelope for automation consumers.
    """
    # Top-level --doctor per hugr CONVENTIONS.md. Intercept before
    # the legacy dispatcher so every owa-* binary picks it up via the
    # shared entry point. --json flips it to machine mode.
    if is_doctor_invocation(argv):
        from owa_core.conventions import emit_doctor
        return emit_doctor(tool, '--json' in argv)

    agent, err_json, filtered = split_mode_flags(argv)
    command = command_name(filtered)

    if agent and command in binary_stdout_commands and '--out' not in filtered:
        return emit_error(
            UsageError('--agent requires JSON stdout; write binary output with --out'),
            tool=tool,
            command=command,
            err_json=err_json,
        )

    with _mode_environment(tool, command, err_json):
        if not agent:
            try:
                return int(dispatch(filtered) or 0)
            except OwaError as error:
                return emit_error(error)
            except SystemExit as exc:
                return int(exc.code or 0)

        captured = io.StringIO()
        try:
            with contextlib.redirect_stdout(captured):
                rc = int(dispatch(filtered) or 0)
        except OwaError as error:
            rc = emit_error(error)
        except SystemExit as exc:
            rc = int(exc.code or 0)

        output = captured.getvalue()
        if rc != 0:
            sys.stdout.write(output)
            return rc

        text = output.strip()
        if text:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                sys.stdout.write(output)
                return emit_error(
                    UsageError('--agent requires JSON stdout; remove --pretty or --ndjson'),
                    tool=tool,
                    command=command,
                    err_json=err_json,
                )
        else:
            data = None
        json.dump(envelope(tool, command, data), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write('\n')
        return 0
