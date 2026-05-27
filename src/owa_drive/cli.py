"""Argument parsing and dispatch for `owa-drive`.

Subcommands: ls, get, put, rm. Address by path
(`/Documents/foo.txt`); the resolver translates to the Graph
`root:/path:/...` form.

Binary handling:
- `get` writes content to a file (`--out`) or stdout (default).
- `put` reads from a file or stdin (`-`).
"""
import json
import os
import sys

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core import tty as tty_mod
from owa_core.errors import UsageError, emit_error, emit_message

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from . import paths as paths_mod
from .format import format_item_pretty, format_items_pretty
from .items import normalize_item


def _error(msg):
    emit_message(msg)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('DRIVE_DEBUG') == '1'


def _require_value(flag, args):
    if not args:
        raise UsageError(f'{flag} requires a value')
    return args[0], args[1:]


def print_help():
    print("""owa-drive - OneDrive CRUD CLI for Outlook / Microsoft 365

Usage: owa-drive <command> [options]

Global options:
  --debug, --verbose  Print HTTP requests and response bodies on errors
                      (also: DRIVE_DEBUG=1)
  --profile <alias>   Forward to owa-piggy as --profile <alias>.

Commands (unix-style verbs; suite-canonical aliases in parentheses):
  ls [path]           List a folder (default: drive root).  (alias: list)
  show <path>         Show metadata for one item.
  get <path>          Download file content.  (alias: download)
                      Default: stream to stdout.
                      With --out <local>: write to that path.
  put <local> <remote-path>                                 (alias: upload)
                      Upload a file of any size to <remote-path>.
                      Small files use a single PUT; larger files use a
                      Graph resumable upload session automatically.
                      <local>=='-' reads from stdin.
  rm <path>           Delete an item (requires --confirm).   (alias: delete)
  refresh             Force a token refresh and verify auth.
  config              View or update configuration.
  help                Show this help.

Common options:
  --pretty            Human-readable output (ls / show; default: JSON).
  --all               Follow @odata.nextLink until exhausted (ls).
  --confirm           Skip confirmation prompts (rm).
  --out <local>       Write download to this path instead of stdout (get).

Examples:
  owa-drive ls --pretty
  owa-drive ls "/Documents" --pretty
  owa-drive show "/Documents/Q1 plan.docx" --pretty
  owa-drive get "/Documents/foo.txt" --out ./foo.txt
  owa-drive get "/Documents/foo.txt" | jq .   # if it's JSON
  owa-drive put ./foo.txt "/Documents/foo.txt"
  cat ./report.md | owa-drive put - "/Documents/report.md"
  owa-drive rm "/Documents/old.txt" --confirm
""")
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_ls(args, config, access_token, api_base):
    pretty = False
    all_pages = False
    path = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--all':
            all_pages = True
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not path:
            path = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')

    endpoint = paths_mod.children_endpoint(path)
    if all_pages:
        items = api_mod.paginate_all(
            api_base, endpoint, access_token, debug=_debug_enabled(config),
        )
        if items is None:
            return 1
        out = [normalize_item(i) for i in items]
        if pretty:
            print(format_items_pretty(out))
        else:
            print(json.dumps(out))
        return 0
    payload = api_mod.api_request(
        'GET', api_base, endpoint, access_token,
        debug=_debug_enabled(config),
    )
    if payload is None:
        return 1
    items = payload.get('value') or []
    out = [normalize_item(i) for i in items]
    if pretty:
        print(format_items_pretty(out))
    else:
        print(json.dumps(out))
    return 0


def cmd_show(args, config, access_token, api_base):
    pretty = False
    path = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not path:
            path = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')

    if not path:
        _error('show requires a path')
        return 1
    endpoint = paths_mod.item_endpoint(path)
    payload = api_mod.api_request(
        'GET', api_base, endpoint, access_token,
        debug=_debug_enabled(config),
    )
    if payload is None:
        return 1
    item = normalize_item(payload)
    if pretty:
        print(format_item_pretty(item))
    else:
        print(json.dumps(item))
    return 0


def cmd_get(args, config, access_token, api_base):
    out_path = ''
    path = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--out':
            out_path, args = _require_value(flag, args)
        elif flag.startswith('-') and flag != '-':
            raise UsageError(f'Unknown flag: {flag}')
        elif not path:
            path = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')

    if not path:
        _error('get requires a path')
        return 1

    try:
        endpoint = paths_mod.content_endpoint(path)
    except ValueError as exc:
        _error(str(exc))
        return 1

    content = api_mod.api_get_binary(
        api_base, endpoint, access_token,
        debug=_debug_enabled(config),
    )
    if content is None:
        return 1

    if out_path:
        with open(out_path, 'wb') as fh:
            fh.write(content)
        _info(f'wrote {len(content)} bytes to {out_path}')
    else:
        # Write raw bytes to stdout. Don't print a trailing newline -
        # the caller pipes to jq/cat/etc and expects exact bytes.
        sys.stdout.buffer.write(content)
    return 0


def cmd_put(args, config, access_token, api_base):
    local = ''
    remote = ''
    while args:
        flag, args = args[0], args[1:]
        if flag.startswith('-') and flag != '-':
            raise UsageError(f'Unknown flag: {flag}')
        elif not local:
            local = flag
        elif not remote:
            remote = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')

    if not local or not remote:
        _error('put requires <local> and <remote-path>')
        return 1

    if local == '-':
        data = sys.stdin.buffer.read()
    else:
        try:
            with open(local, 'rb') as fh:
                data = fh.read()
        except OSError as exc:
            _error(f'cannot read {local}: {exc}')
            return 1

    if len(data) > api_mod.UPLOAD_LIMIT_BYTES:
        try:
            session_endpoint = paths_mod.upload_session_endpoint(remote)
        except ValueError as exc:
            _error(str(exc))
            return 1
        _info(f'uploading {len(data)} bytes via upload session...')
        payload = api_mod.api_upload_session(
            api_base, session_endpoint, access_token, data,
            debug=_debug_enabled(config),
        )
    else:
        try:
            endpoint = paths_mod.content_endpoint(remote)
        except ValueError as exc:
            _error(str(exc))
            return 1
        payload = api_mod.api_put_binary(
            api_base, endpoint, access_token, data,
            debug=_debug_enabled(config),
        )
    if payload is None:
        return 1
    item = normalize_item(payload) if isinstance(payload, dict) else {}
    print(json.dumps(item))
    return 0


def cmd_rm(args, config, access_token, api_base):
    confirm = False
    path = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--confirm':
            confirm = True
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not path:
            path = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')

    if not path:
        _error('rm requires a path')
        return 1

    try:
        endpoint = paths_mod.delete_endpoint(path)
    except ValueError as exc:
        _error(str(exc))
        return 1

    if not confirm:
        try:
            tty_mod.require_confirm_or_tty(action='rm')
        except UsageError as error:
            return emit_error(error)
        _info(f'about to delete: {path}')
        if not tty_mod.confirm('type "yes" to proceed: ', accepted=('yes',)):
            _info('aborted')
            return 1

    payload = api_mod.api_request(
        'DELETE', api_base, endpoint, access_token,
        debug=_debug_enabled(config),
    )
    if payload is None:
        return 1
    _info(f'deleted: {path}')
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
    if config.get('owa_piggy_profile'):
        _info(f"  owa_piggy_profile={config.get('owa_piggy_profile')}")
    else:
        _info('  owa_piggy_profile=(not set - owa-piggy picks its default)')
    return 0


def cmd_refresh(args, config):
    if args:
        raise UsageError(f'Unknown flag: {args[0]}')
    _info('Refreshing token...')
    access = auth_mod.do_token_refresh(config, debug=_debug_enabled(config))
    if not access:
        _error('Token refresh failed.')
        return 1
    me = api_mod.api_request(
        'GET', 'https://graph.microsoft.com/v1.0', 'me', access,
        debug=_debug_enabled(config),
    )
    if not isinstance(me, dict):
        _error('Auth verification failed.')
        return 1
    name = me.get('displayName')
    if name:
        _info(f'Authenticated as {name}')
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

AUTHED_COMMANDS = {'ls', 'show', 'get', 'put', 'rm'}


def _command_name(argv):
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--debug', '--verbose'):
            i += 1
            continue
        if a == '--profile':
            i += 2
            continue
        return a
    return ''


_LS_FLAGS = [
    schema_mod.flag('<path>', summary='Folder path (positional, defaults to drive root)'),
    schema_mod.flag('--all', summary='Follow @odata.nextLink until exhausted'),
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
]

_SHOW_FLAGS = [
    schema_mod.flag('<path>', summary='Item path (positional)', required=True),
    schema_mod.flag('--pretty', summary='Human-readable view (default: JSON)'),
]

_GET_FLAGS = [
    schema_mod.flag('<path>', summary='Remote item path (positional)', required=True),
    schema_mod.flag('--out', value='<local-path>', summary='Write to file instead of stdout'),
]

_PUT_FLAGS = [
    schema_mod.flag('<local>', summary='Local file path or - to read stdin (positional)', required=True),
    schema_mod.flag('<remote-path>', summary='Destination path on the drive (positional)', required=True),
]

_RM_FLAGS = [
    schema_mod.flag('<path>', summary='Item path (positional)', required=True),
    schema_mod.flag('--confirm', summary='Skip confirmation prompt'),
]

_CONFIG_FLAGS = [
    schema_mod.flag('--profile', value='<alias>', summary='Pin a default owa-piggy profile alias (owa_piggy_profile)'),
]

COMMAND_SCHEMA = [
    schema_mod.command('ls', 'List a folder', auth='graph', flags=_LS_FLAGS, aliases=['list']),
    schema_mod.command('show', 'Show item metadata', auth='graph', flags=_SHOW_FLAGS),
    schema_mod.command('get', 'Download file content', auth='graph', output='bytes', flags=_GET_FLAGS, aliases=['download']),
    schema_mod.command('put', 'Upload a file of any size', auth='graph', mutates=True, idempotent=True, flags=_PUT_FLAGS, aliases=['upload']),
    schema_mod.command(
        'rm',
        'Delete an item',
        auth='graph',
        mutates=True,
        destructive=True,
        confirmation=True,
        idempotent=False,
        flags=_RM_FLAGS,
        aliases=['delete'],
    ),
    schema_mod.command('refresh', 'Force a token refresh', auth='graph'),
    schema_mod.command('config', 'View or update configuration', mutates=True, flags=_CONFIG_FLAGS),
]


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-drive', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled

    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] == '--version':
        print(f'owa-drive {__version__}')
        return 0

    debug_flag = False
    profile_override = ''
    is_config_cmd = _command_name(argv) == 'config'
    filtered = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--debug', '--verbose'):
            debug_flag = True
        elif a == '--profile' and not (is_config_cmd and 'config' in filtered):
            if i + 1 >= len(argv):
                _error('--profile requires a value'); return 1
            profile_override = argv[i + 1]
            i += 2
            continue
        else:
            filtered.append(a)
        i += 1
    argv = filtered

    if not argv:
        print_help()
        return 0

    cmd, rest = argv[0], argv[1:]
    # ls/get/put/rm are the primary verbs; list/download/upload/delete are
    # accepted as suite-canonical aliases (resolved to the canonical name
    # before help and dispatch so both share one path).
    cmd = schema_mod.resolve_alias(cmd, COMMAND_SCHEMA)

    help_rc = schema_mod.maybe_emit_subcommand_help(
        cmd, rest, tool='owa-drive', commands=COMMAND_SCHEMA,
    )
    if help_rc is not None:
        return help_rc

    config = config_mod.load_config()
    if debug_flag:
        config['debug'] = True
        _info('DEBUG: verbose logging enabled')
    if profile_override:
        config['owa_piggy_profile'] = profile_override

    if cmd == 'config':
        return cmd_config(rest, config)
    if cmd == 'refresh':
        return cmd_refresh(rest, config)

    if cmd not in AUTHED_COMMANDS:
        _error(f"Unknown command: {cmd}. Run 'owa-drive help' for usage.")
        return 1

    access_token, api_base = auth_mod.setup_auth(
        config, debug=_debug_enabled(config),
    )

    if cmd == 'ls':
        return cmd_ls(rest, config, access_token, api_base)
    if cmd == 'show':
        return cmd_show(rest, config, access_token, api_base)
    if cmd == 'get':
        return cmd_get(rest, config, access_token, api_base)
    if cmd == 'put':
        return cmd_put(rest, config, access_token, api_base)
    if cmd == 'rm':
        return cmd_rm(rest, config, access_token, api_base)

    return 1


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-drive',
        sys.argv[1:] if argv is None else argv,
        _main,
        binary_stdout_commands=('get',),
    )
