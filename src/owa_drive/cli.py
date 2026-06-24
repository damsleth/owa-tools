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

from owa_core import http as http_mod
from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core import tty as tty_mod
from owa_core.errors import (
    ConflictError,
    InternalError,
    NetworkError,
    NotFoundError,
    OwaError,
    RateLimitedError,
    UsageError,
    emit_error,
    emit_message,
)

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from . import paths as paths_mod
from .format import format_item_pretty, format_items_pretty
from .items import normalize_item

# Recoverable per-file errors that batch `put` tolerates: one bad file must
# not abort the rest. Auth/scope errors are deliberately excluded so they
# still propagate (re-auth is needed before any further file can succeed).
_RECOVERABLE_UPLOAD_ERRORS = (
    NetworkError,
    NotFoundError,
    ConflictError,
    RateLimitedError,
    InternalError,
)


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
                      Refuses to overwrite an existing remote item
                      (exit 15) unless --force is passed; OneDrive
                      versioning preserves overwritten content.
  put <local>... <remote-dir>                                (batch)
                      Upload multiple files to <remote-dir>; each ends
                      up at <remote-dir>/<basename>. Existing files are
                      skipped (use --force to overwrite); per-file
                      failures are recorded but never abort the batch.
                      Stdout is one JSON summary with uploaded /
                      skipped / failed lists.
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
    print(schema_mod.MULTI_PROFILE_HELP)
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
        raise UsageError('show requires a path')
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
    force = False
    path = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--out':
            out_path, args = _require_value(flag, args)
        elif flag == '--force':
            force = True
        elif flag.startswith('-') and flag != '-':
            raise UsageError(f'Unknown flag: {flag}')
        elif not path:
            path = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')

    if not path:
        raise UsageError('get requires a path')

    # Refuse to clobber an existing local file unless --force (exit 15).
    # Mirrors `put`'s overwrite guard - downloads are data-loss too.
    if out_path and not force and os.path.exists(out_path):
        raise ConflictError(
            f'local file already exists: {out_path} (pass --force to overwrite)'
        )

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


def _remote_exists(api_base, remote, access_token, debug):
    """Silent existence check. Returns True/False/None (None = error).

    OneDrive enables versioning by default, so refusing to overwrite is a
    bandwidth optimisation - it lets `put` skip a re-upload when the
    remote item is already present. Returns None (instead of False) on
    transient errors so callers can decide whether to proceed or abort;
    we proceed by default (the user asked us to upload).
    """
    if not remote or remote == '/':
        return False
    url = f'{api_base}/{paths_mod.item_endpoint(remote).lstrip("/")}'
    try:
        response = http_mod.request('GET', url, token=access_token, debug=debug)
    except NotFoundError:
        return False
    except OwaError:
        return None
    return bool(response.json)


def _upload_one(local, remote, *, config, access_token, api_base, debug):
    """Read and PUT a single file. Returns ('uploaded', item) or
    ('failed', None). Selects the simple PUT path or the upload-session
    path based on size, mirroring the per-file logic that single-file
    `put` has used since v0.1.
    """
    if local == '-':
        data = sys.stdin.buffer.read()
    else:
        try:
            with open(local, 'rb') as fh:
                data = fh.read()
        except OSError as exc:
            _error(f'cannot read {local}: {exc}')
            return 'failed', None

    if len(data) > api_mod.UPLOAD_LIMIT_BYTES:
        try:
            session_endpoint = paths_mod.upload_session_endpoint(remote)
        except ValueError as exc:
            _error(str(exc))
            return 'failed', None
        _info(f'uploading {len(data)} bytes via upload session...')
        payload = api_mod.api_upload_session(
            api_base, session_endpoint, access_token, data, debug=debug,
        )
    else:
        try:
            endpoint = paths_mod.content_endpoint(remote)
        except ValueError as exc:
            _error(str(exc))
            return 'failed', None
        payload = api_mod.api_put_binary(
            api_base, endpoint, access_token, data, debug=debug,
        )
    if payload is None:
        return 'failed', None
    item = normalize_item(payload) if isinstance(payload, dict) else {}
    return 'uploaded', item


def _resolve_batch_remote(remote_dir, local):
    """Build the per-file remote path for batch mode.

    `remote_dir` is the trailing positional in a multi-file `put`. The
    upload target is `<remote_dir>/<basename(local)>`; stdin (`-`) is
    rejected for batch mode since there is no filename to derive.
    """
    if local == '-':
        raise UsageError(
            "batch put cannot read from stdin ('-'); use single-file put "
            "with an explicit <remote-path> instead"
        )
    base = os.path.basename(local.rstrip('/'))
    if not base:
        raise UsageError(f'cannot derive remote name from {local!r}')
    return f'{remote_dir.rstrip("/")}/{base}'


def cmd_put(args, config, access_token, api_base):
    force = False
    positional = []
    while args:
        flag, args = args[0], args[1:]
        if flag == '--force':
            force = True
        elif flag.startswith('-') and flag != '-':
            raise UsageError(f'Unknown flag: {flag}')
        else:
            positional.append(flag)

    if len(positional) < 2:
        raise UsageError('put requires <local> and <remote-path>')

    debug = _debug_enabled(config)
    batch = len(positional) > 2
    if batch:
        remote_dir = positional[-1]
        locals_ = positional[:-1]
    else:
        remote_dir = None
        locals_ = [positional[0]]

    uploaded = []
    skipped = []
    failed = []

    for local in locals_:
        remote = (
            _resolve_batch_remote(remote_dir, local)
            if batch else positional[1]
        )

        if not force:
            exists = _remote_exists(api_base, remote, access_token, debug)
            if exists is True:
                # Skip-and-continue: in batch mode the rest of the files
                # MUST still upload (the whole point of the batch). In
                # single-file mode the user gets exit 15 below.
                _info(f'skip (exists, no --force): {remote}')
                skipped.append({'local': local, 'remote': remote})
                continue

        try:
            status, item = _upload_one(
                local, remote,
                config=config, access_token=access_token,
                api_base=api_base, debug=debug,
            )
        except _RECOVERABLE_UPLOAD_ERRORS as exc:
            # Batch mode is fault-tolerant per file: a transient upload error
            # on one file must not abort the rest. Single-file mode re-raises
            # so the typed exit code (10/13/14/15/20) still propagates.
            if not batch:
                raise
            _error(f'failed {remote}: {exc}')
            failed.append({'local': local, 'remote': remote})
            continue
        if status == 'uploaded':
            uploaded.append({'local': local, 'remote': remote, 'item': item})
        else:
            failed.append({'local': local, 'remote': remote})

    if batch:
        print(json.dumps({
            'uploaded': uploaded,
            'skipped': skipped,
            'failed': failed,
        }))
        # 0 if no genuine failures (skips count as success - they were
        # intentional). 1 if any per-file upload failed.
        return 1 if failed else 0

    # Single-file mode: preserve the original "print item JSON, exit 0/1"
    # contract. A skip becomes exit 15 (CONFLICT) so a caller without
    # --force learns they need to opt in to overwrite; in a shell `for`
    # loop the conflict surfaces per-invocation but does not abort the loop.
    if skipped:
        raise ConflictError(
            f'remote already exists: {skipped[0]["remote"]} '
            '(pass --force to overwrite)'
        )
    if failed:
        return 1
    print(json.dumps(uploaded[0]['item']))
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
        raise UsageError('rm requires a path')

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
    schema_mod.flag('--force', summary='Overwrite an existing local --out file (default: refuse with exit 15)'),
]

_PUT_FLAGS = [
    schema_mod.flag('<local>', summary='Local file path, - for stdin, or multiple files (positional)', required=True),
    schema_mod.flag('<remote-path>', summary='Destination path; in batch mode (multiple <local>) this is the destination directory (positional)', required=True),
    schema_mod.flag('--force', summary='Overwrite existing remote items (default: refuse with exit 15; in batch mode: skip existing)'),
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
    if argv[0] in ('--version', '-v'):
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
                raise UsageError('--profile requires a value')
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
        raise UsageError(f"Unknown command: {cmd}. Run 'owa-drive help' for usage.")

    schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)

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


# Delegated scopes that grant each drive command (any-of), used by the
# --profile all fan-out to silently skip profiles with no OneDrive/SharePoint
# file access (e.g. a DevOps-only graph token carrying no Files/Sites scope).
# `get` is binary (can't fan out) and refresh/config are local, so absent.
_DRIVE_SCOPES = frozenset({
    'Files.Read', 'Files.ReadWrite',
    'Files.Read.All', 'Files.ReadWrite.All',
    'Sites.Read.All', 'Sites.ReadWrite.All',
})
COMMAND_SCOPES = {cmd: _DRIVE_SCOPES for cmd in ('ls', 'show', 'put', 'rm')}


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-drive',
        sys.argv[1:] if argv is None else argv,
        _main,
        binary_stdout_commands=('get',),
        audience=auth_mod.AUDIENCE,
        command_scopes=COMMAND_SCOPES,
    )
