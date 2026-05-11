"""Small schema helpers for command-surface introspection."""
import json
import sys

from .version import suite_version

SCHEMA_VERSION = 1


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
