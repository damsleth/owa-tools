"""Small schema helpers for command-surface introspection."""
import json
import sys

from .version import suite_version

SCHEMA_VERSION = 1

HELP_TOKENS = ('--help', '-h')


def flag(name, *, value=None, summary='', required=False, repeatable=False):
    """Build a single flag spec for a command's `flags` list.

    Args:
        name: Flag name as shown on the command line (e.g. '--pretty', '--id').
        value: Placeholder for the value an arg-taking flag expects
               (e.g. '<event-id>'). None for boolean flags.
        summary: One-line human description.
        required: True if the subcommand rejects invocations without it.
        repeatable: True if the flag may be passed multiple times.
    """
    row = {'name': name}
    if value is not None:
        row['value'] = value
    if summary:
        row['summary'] = summary
    if required:
        row['required'] = True
    if repeatable:
        row['repeatable'] = True
    return row


def command(
    name,
    summary='',
    auth=None,
    output='json',
    flags=None,
    mutates=False,
    destructive=False,
    confirmation=False,
    idempotent=None,
):
    row = {
        'name': name,
        'summary': summary,
        'output': {'type': output},
        'flags': list(flags or []),
    }
    if auth:
        row['auth'] = {'audience': auth}
    if mutates:
        row['mutates'] = True
    if destructive:
        row['destructive'] = True
    if confirmation:
        row['confirmation'] = {'flag': '--confirm'}
    if idempotent is not None:
        row['idempotent'] = bool(idempotent)
    return row


def schema_for(tool, commands):
    return {
        'tool': tool,
        'suite': 'owa-tools',
        'version': suite_version(),
        'schema_version': SCHEMA_VERSION,
        'commands': list(commands),
    }


def emit_json(payload):
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


def maybe_emit_schema(argv, *, tool, commands):
    """Handle `schema`, `schema <command>`, and `--help --json`.

    Returns an exit code when handled, otherwise None.
    """
    if argv in (['--help', '--json'], ['help', '--json']):
        return emit_json(schema_for(tool, commands))
    if not argv or argv[0] != 'schema':
        return None
    schema = schema_for(tool, commands)
    if len(argv) > 2:
        print('schema accepts at most one command name', file=sys.stderr)
        return 2
    if len(argv) == 2:
        name = argv[1]
        matched = [cmd for cmd in schema['commands'] if cmd['name'] == name]
        if not matched:
            print(f'unknown schema command: {name}', file=sys.stderr)
            return 2
        schema = {**schema, 'commands': matched}
    return emit_json(schema)


def _flag_left(entry):
    """Render the left column for a flag entry built by `flag()`."""
    name = entry.get('name', '')
    value = entry.get('value')
    return f'{name} {value}' if value else name


def _flag_right(entry):
    """Render the right column (summary + required marker)."""
    parts = []
    summary = entry.get('summary') or ''
    if summary:
        parts.append(summary)
    if entry.get('required'):
        parts.append('(required)')
    if entry.get('repeatable'):
        parts.append('(repeatable)')
    return ' '.join(parts)


def render_command_help(tool, cmd_dict, *, stream=None):
    """Write per-subcommand help to `stream` (default stdout).

    Output shape:

        Usage: <tool> <cmd> [options]

          <summary>

        Flags:
          --id <event-id>   Event ID (required)
          --pretty          Human-readable table
    """
    stream = stream or sys.stdout
    name = cmd_dict.get('name', '')
    summary = cmd_dict.get('summary') or ''
    flags = cmd_dict.get('flags') or []

    stream.write(f'Usage: {tool} {name} [options]\n')
    if summary:
        stream.write(f'\n  {summary}\n')
    if flags:
        rows = [(_flag_left(f), _flag_right(f)) for f in flags]
        width = max(len(left) for left, _ in rows)
        stream.write('\nFlags:\n')
        for left, right in rows:
            if right:
                stream.write(f'  {left:<{width}}  {right}\n')
            else:
                stream.write(f'  {left}\n')
    else:
        stream.write('\n  (no flags)\n')

    notes = []
    if cmd_dict.get('mutates'):
        notes.append('mutates state')
    if cmd_dict.get('destructive'):
        notes.append('destructive')
    if cmd_dict.get('confirmation'):
        confirm_flag = cmd_dict['confirmation'].get('flag', '--confirm')
        notes.append(f'requires {confirm_flag} or interactive TTY')
    if cmd_dict.get('idempotent') is False:
        notes.append('not idempotent')
    auth = cmd_dict.get('auth') or {}
    if auth.get('audience'):
        notes.append(f"auth audience: {auth['audience']}")
    if notes:
        stream.write('\nNotes:\n')
        for note in notes:
            stream.write(f'  - {note}\n')

    return 0


def is_help_token(token):
    return token in HELP_TOKENS


def maybe_emit_subcommand_help(cmd, rest, *, tool, commands):
    """If `rest` is an explicit help request for a known command,
    write per-command help to stdout and return 0. Otherwise return None.

    Intended to short-circuit before auth or HTTP setup. Only a single
    `--help` or `-h` token is treated as help; free-text commands and
    value-taking flags must be able to accept values such as "help".
    """
    if len(rest) != 1 or not is_help_token(rest[0]):
        return None
    matched = next((c for c in commands if c.get('name') == cmd), None)
    if matched is None:
        return None
    return render_command_help(tool, matched)
