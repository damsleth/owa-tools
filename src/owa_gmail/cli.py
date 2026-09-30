"""Argument parsing and dispatch for `owa-gmail`."""
import json
import os
import sys

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core.errors import ConflictError, UsageError, _require_value

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from .format import format_labels_pretty, format_message_pretty, format_messages_pretty
from .messages import b64url_decode, build_list_query, normalize_label, normalize_message


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('GMAIL_DEBUG') == '1'


def print_help():
    print("""owa-gmail - read-only Gmail CLI (owa-piggy Google profile)

Usage: owa-gmail <command> [options]

Global options:
  --debug, --verbose  Print HTTP requests on stderr (also: GMAIL_DEBUG=1)
  --profile <alias>   owa-piggy Google profile (default: the only one)

Commands:
  messages            List messages (newest first).
  show <id>           One message: headers, bodies, attachment metadata.
  get <id>            The original RFC 822 message (.eml bytes).
  attachments <message-id> <attachment-id>
                      Download one attachment's bytes.
  labels              List labels.
  refresh             Force a token refresh and verify auth.
  config              View or pin the default profile.
  help                Show this help.

messages options:
  --from <addr> --to <addr> --subject <text> --label <name>
  --unread --has-attachment --since YYYY-MM-DD --until YYYY-MM-DD
  --search <gmail query>   Raw Gmail search; replaces the flags above
  --max-results <n>        Page size (default 25)
  --page-token <token>     Continue from a previous page
  --all                    Follow every page
  --with-body              Fetch each message in full (one extra call per
                           message: Gmail's list returns only ids)
  --pretty

get / attachments options:
  --out <file>        Write to a file instead of stdout
  --force             Overwrite an existing --out file (default: exit 15)

Examples:
  owa-gmail messages --unread --pretty
  owa-gmail messages --from boss@example.com --since 2026-09-01
  owa-gmail show 18c2f... --pretty
  owa-gmail get 18c2f... --out mail.eml
""")
    print(schema_mod.MULTI_PROFILE_HELP)
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


def _int(flag, args):
    value, args = _require_value(flag, args)
    try:
        return int(value), args
    except ValueError as exc:
        raise UsageError(f'{flag} requires an integer') from exc


def cmd_messages(args, config, token, base):
    q = {}
    max_results = 25
    follow = with_body = pretty = False
    string_flags = {'--from': 'sender', '--to': 'to', '--subject': 'subject', '--label': 'label',
                    '--since': 'since', '--until': 'until', '--search': 'search',
                    '--page-token': 'page_token'}
    while args:
        flag, args = args[0], args[1:]
        if flag in string_flags:
            q[string_flags[flag]], args = _require_value(flag, args)
        elif flag == '--max-results':
            max_results, args = _int(flag, args)
        elif flag == '--unread':
            q['unread'] = True
        elif flag == '--has-attachment':
            q['has_attachment'] = True
        elif flag == '--all':
            follow = True
        elif flag == '--with-body':
            with_body = True
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if max_results < 1 or max_results > 500:
        raise UsageError('--max-results must be between 1 and 500')
    debug = _debug_enabled(config)
    params = build_list_query(max_results=max_results, **q)
    ids, next_token = api_mod.paginate(
        base, 'messages', token, params, 'messages', max_pages=None if follow else 1, debug=debug,
    )
    # Gmail's list returns only {id, threadId}: headers need one GET per
    # message. `metadata` keeps that call small; `full` adds the bodies.
    fmt = {'format': 'full'} if with_body else {'format': 'metadata'}
    rows = [
        normalize_message(
            api_mod.api_get(base, f'messages/{m["id"]}', token, params=fmt, debug=debug),
            with_body=with_body,
        )
        for m in ids
    ]
    if pretty:
        print(format_messages_pretty(rows))
        if next_token:
            print(f'\n(more: --page-token {next_token})')
    elif next_token and not follow:
        print(json.dumps({'messages': rows, 'next_page_token': next_token}, ensure_ascii=False))
    else:
        print(json.dumps(rows, ensure_ascii=False))
    return 0


def _positional(args, names, extra_flags=()):
    values, opts = [], {}
    while args:
        flag, args = args[0], args[1:]
        if flag == '--out' and '--out' in extra_flags:
            opts['out'], args = _require_value(flag, args)
        elif flag in extra_flags:
            opts[flag.lstrip('-')] = True
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        else:
            values.append(flag)
    if len(values) != len(names):
        raise UsageError(f'expected {" ".join(names)}')
    return values, opts


def cmd_show(args, config, token, base):
    (msg_id,), opts = _positional(args, ['<id>'], ('--pretty',))
    raw = api_mod.api_get(base, f'messages/{msg_id}', token, params={'format': 'full'},
                          debug=_debug_enabled(config))
    message = normalize_message(raw, with_body=True)
    if opts.get('pretty'):
        print(format_message_pretty(message))
    else:
        print(json.dumps(message, ensure_ascii=False))
    return 0


def _write_bytes(data, opts):
    out = opts.get('out')
    if not out:
        sys.stdout.buffer.write(data)
        return 0
    if not opts.get('force') and os.path.exists(out):
        raise ConflictError(f'local file already exists: {out} (pass --force to overwrite)')
    with open(out, 'wb') as fh:
        fh.write(data)
    _info(f'wrote {len(data)} bytes to {out}')
    return 0


def cmd_get(args, config, token, base):
    (msg_id,), opts = _positional(args, ['<id>'], ('--out', '--force'))
    raw = api_mod.api_get(base, f'messages/{msg_id}', token, params={'format': 'raw'},
                          debug=_debug_enabled(config))
    return _write_bytes(b64url_decode(raw.get('raw', '')), opts)


def cmd_attachments(args, config, token, base):
    (msg_id, att_id), opts = _positional(args, ['<message-id>', '<attachment-id>'], ('--out', '--force'))
    raw = api_mod.api_get(base, f'messages/{msg_id}/attachments/{att_id}', token,
                          debug=_debug_enabled(config))
    return _write_bytes(b64url_decode(raw.get('data', '')), opts)


def cmd_labels(args, config, token, base):
    _, opts = _positional(args, [], ('--pretty',))
    payload = api_mod.api_get(base, 'labels', token, debug=_debug_enabled(config)) or {}
    rows = sorted((normalize_label(r) for r in payload.get('labels') or []),
                  key=lambda r: (r['type'] != 'system', r['name'].lower()))
    print(format_labels_pretty(rows) if opts.get('pretty') else json.dumps(rows, ensure_ascii=False))
    return 0


def cmd_refresh(args, config):
    if args:
        raise UsageError(f'Unknown flag: {args[0]}')
    token, base = auth_mod.setup_auth(config, debug=_debug_enabled(config))
    me = api_mod.api_get(base, 'profile', token, debug=_debug_enabled(config)) or {}
    _info(f"Authenticated as {me.get('emailAddress', '?')}")
    return 0


def cmd_config(args, config):
    profile = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--profile':
            profile, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if profile:
        config_mod.config_set('owa_piggy_profile', profile)
        _info(f'default profile saved: {profile}')
        return 0
    _info(f'Config file: {config_mod.CONFIG_PATH}')
    _info(f"  owa_piggy_profile={config.get('owa_piggy_profile') or '(not set - the only Google profile)'}")
    return 0


AUTHED_COMMANDS = {
    'messages': cmd_messages,
    'show': cmd_show,
    'get': cmd_get,
    'attachments': cmd_attachments,
    'labels': cmd_labels,
}

_PRETTY = schema_mod.flag('--pretty', summary='Human-readable output (default: JSON)')
_OUT = [
    schema_mod.flag('--out', value='<file>', summary='Write to a file instead of stdout'),
    schema_mod.flag('--force', summary='Overwrite an existing --out file (default: exit 15)'),
]

COMMAND_SCHEMA = [
    schema_mod.command('messages', 'List messages', auth=auth_mod.AUDIENCE, flags=[
        schema_mod.flag('--from', value='<addr>', summary='Sender'),
        schema_mod.flag('--to', value='<addr>', summary='Recipient'),
        schema_mod.flag('--subject', value='<text>', summary='Subject contains'),
        schema_mod.flag('--label', value='<name>', summary='Label name'),
        schema_mod.flag('--unread', summary='Unread only'),
        schema_mod.flag('--has-attachment', summary='With attachments only'),
        schema_mod.flag('--since', value='<YYYY-MM-DD>', summary='On or after'),
        schema_mod.flag('--until', value='<YYYY-MM-DD>', summary='Before'),
        schema_mod.flag('--search', value='<query>', summary='Raw Gmail search (replaces the filters)'),
        schema_mod.flag('--max-results', value='<n>', summary='Page size (default 25, max 500)'),
        schema_mod.flag('--page-token', value='<token>', summary='Continue from a previous page'),
        schema_mod.flag('--all', summary='Follow every page'),
        schema_mod.flag('--with-body', summary='Fetch full bodies (one call per message)'),
        _PRETTY,
    ]),
    schema_mod.command('show', 'Show one message', auth=auth_mod.AUDIENCE, flags=[
        schema_mod.flag('<id>', summary='Message id', required=True), _PRETTY,
    ]),
    schema_mod.command('get', 'Download the raw RFC 822 message', auth=auth_mod.AUDIENCE, output='bytes', flags=[
        schema_mod.flag('<id>', summary='Message id', required=True), *_OUT,
    ]),
    schema_mod.command('attachments', 'Download one attachment', auth=auth_mod.AUDIENCE, output='bytes', flags=[
        schema_mod.flag('<message-id>', summary='Message id', required=True),
        schema_mod.flag('<attachment-id>', summary='Attachment id (from show)', required=True),
        *_OUT,
    ]),
    schema_mod.command('labels', 'List labels', auth=auth_mod.AUDIENCE, flags=[_PRETTY]),
    schema_mod.command('refresh', 'Force a token refresh', auth=auth_mod.AUDIENCE),
    schema_mod.command('config', 'View or update configuration', mutates=True, flags=[
        schema_mod.flag('--profile', value='<alias>', summary='Pin a default owa-piggy profile alias'),
    ]),
]


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-gmail', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled
    if not argv or argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] in ('--version', '-v'):
        print(f'owa-gmail {__version__}')
        return 0

    argv, debug_flag, profile_override = mode_mod.strip_global_flags(argv)
    if not argv:
        print_help()
        return 0
    cmd, rest = argv[0], argv[1:]
    help_rc = schema_mod.maybe_emit_subcommand_help(cmd, rest, tool='owa-gmail', commands=COMMAND_SCHEMA)
    if help_rc is not None:
        return help_rc

    config = config_mod.load_config()
    if debug_flag:
        config['debug'] = True
    if profile_override:
        config['owa_piggy_profile'] = profile_override
    if cmd == 'config':
        return cmd_config(rest, config)
    if cmd == 'refresh':
        return cmd_refresh(rest, config)
    if cmd not in AUTHED_COMMANDS:
        raise UsageError(f"Unknown command: {cmd}. Run 'owa-gmail help' for usage.")
    schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)
    token, base = auth_mod.setup_auth(config, debug=_debug_enabled(config))
    return AUTHED_COMMANDS[cmd](rest, config, token, base)


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-gmail',
        sys.argv[1:] if argv is None else argv,
        _main,
        binary_stdout_commands=('get', 'attachments'),
        commands=COMMAND_SCHEMA,
        service=auth_mod.SERVICE,
    )
