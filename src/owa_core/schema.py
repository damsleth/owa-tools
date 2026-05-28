"""Small schema helpers for command-surface introspection."""
import json
import sys

from .errors import UsageError
from .version import suite_version

SCHEMA_VERSION = 1

HELP_TOKENS = ('--help', '-h')

# One uniform block describing the machine/agent surface every owa-*
# binary exposes. Each tool's print_help() appends this verbatim so the
# contract is documented identically across the suite. Exit codes are
# deliberately omitted here (owa-doctor's `probe` uses its own 0/1/2
# taxonomy); they live in docs/security.md and AGENTS.md.
MACHINE_SURFACE_HELP = """Machine surface (uniform across the owa suite):
  schema [<command>]   Print the JSON command schema (one command if named).
  --help --json        Emit that schema instead of human-readable help.
  --agent              Wrap JSON stdout in a stable {"_owa": ..., "data": ...}
                       envelope for automation (or set OWA_AGENT=1).
  --err-json           Emit structured JSON errors on stderr (or OWA_ERR_JSON=1).
  --doctor [--json]    Print this tool's health / redaction doctor payload.
  --version            Print the suite version."""


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
    aliases=None,
):
    row = {
        'name': name,
        'summary': summary,
        'output': {'type': output},
        'flags': list(flags or []),
    }
    if aliases:
        row['aliases'] = list(aliases)
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


def resolve_alias(cmd, commands):
    """Map a command alias to its canonical name.

    Each command may declare ``aliases`` (e.g. owa-drive's ``rm`` aliases
    ``delete``). Returns the canonical name when ``cmd`` matches a
    declared alias, otherwise ``cmd`` unchanged. Dispatchers call this
    right after reading the subcommand token so the alias and the
    canonical verb share one code path.
    """
    for entry in commands:
        if cmd == entry.get('name'):
            return cmd
        if cmd in (entry.get('aliases') or ()):
            return entry['name']
    return cmd


def pop_positional_id(args):
    """Pull a leading positional identifier out of an arg list.

    Commands that address an item by opaque server id accept the id
    either as ``--id <id>`` or as a bare leading token (so
    ``owa-mail show <id>`` matches ``owa-people show <email>`` and
    ``owa-drive show <path>``). Server ids are base64-ish and never
    start with ``-``, so a leading non-flag token is unambiguous.

    Returns ``(positional_id, remaining_args)``; ``('', args)`` when the
    first token is a flag or the list is empty.
    """
    if args and not args[0].startswith('-'):
        return args[0], args[1:]
    return '', list(args)


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
    aliases = cmd_dict.get('aliases') or []
    if aliases:
        stream.write(f"\n  Aliases: {', '.join(aliases)}\n")
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


def precheck_required_args(cmd, args, *, commands):
    """Validate ``args`` against ``cmd``'s schema before auth setup.

    Raises ``UsageError`` for missing required flags or positional values,
    unknown named flags, and value-taking flags that have no value. Returns
    silently when ``cmd`` is not in ``commands`` (the dispatcher's own
    unknown-command path handles that).

    Only the schema is consulted - per-handler semantic checks (mutual
    exclusion, enum values, etc.) still run in the handler.
    """
    canonical = resolve_alias(cmd, commands)
    matched = next((c for c in commands if c.get('name') == canonical), None)
    if matched is None:
        return

    flag_specs = matched.get('flags') or []
    named_specs = {
        f['name']: f for f in flag_specs
        if not f.get('name', '').startswith('<')
    }
    positional_specs = [
        f for f in flag_specs if f.get('name', '').startswith('<')
    ]
    required_positionals = [f for f in positional_specs if f.get('required')]

    seen_named = set()
    positionals_seen = 0
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith('-') or token == '-':
            positionals_seen += 1
            i += 1
            continue
        spec = named_specs.get(token)
        if spec is None:
            raise UsageError(f'Unknown flag: {token}')
        seen_named.add(token)
        if spec.get('value') is not None:
            if i + 1 >= len(args):
                raise UsageError(f'{token} requires a value')
            i += 2
        else:
            i += 1

    for name, spec in named_specs.items():
        if not spec.get('required'):
            continue
        if name in seen_named:
            continue
        # `--id` is the suite's positional fallback (mail/cal/todo "flag or
        # positional"). Only honour the fallback when no `<...>` positional
        # slot is declared - otherwise the positional belongs to that slot.
        if name == '--id' and not positional_specs and positionals_seen >= 1:
            continue
        raise UsageError(f'{name} is required')

    if positionals_seen < len(required_positionals):
        missing = required_positionals[positionals_seen:]
        names = ' '.join(f['name'] for f in missing)
        raise UsageError(f'{names} is required')


def maybe_emit_subcommand_help(cmd, rest, *, tool, commands):
    """If `rest` is an explicit help request for a known command,
    write per-command help to stdout and return 0. Otherwise return None.

    Intended to short-circuit before auth or HTTP setup. Only a single
    `--help` or `-h` token is treated as help; free-text commands and
    value-taking flags must be able to accept values such as "help".
    """
    if len(rest) != 1 or not is_help_token(rest[0]):
        return None
    canonical = resolve_alias(cmd, commands)
    matched = next((c for c in commands if c.get('name') == canonical), None)
    if matched is None:
        return None
    return render_command_help(tool, matched)
