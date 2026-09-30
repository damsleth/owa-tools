"""Argument parsing and dispatch for `owa-gdrive`."""
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
from .files import (
    FILE_FIELDS,
    FOLDER_MIME,
    LIST_FIELDS,
    build_list_query,
    normalize_file,
    resolve_export_mime,
)
from .format import format_file_pretty, format_files_pretty


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('GDRIVE_DEBUG') == '1'


def print_help():
    print("""owa-gdrive - read-only Google Drive CLI (owa-piggy Google profile)

Usage: owa-gdrive <command> [options]

Global options:
  --debug, --verbose  Print HTTP requests on stderr (also: GDRIVE_DEBUG=1)
  --profile <alias>   owa-piggy Google profile (default: the only one)

Commands:
  ls [folder-id]      List a folder (default: My Drive's top level), or
                      search the whole Drive with --name / --search.
  show <id>           Metadata for one file or folder.
  get <id>            Download a file. Google Docs/Sheets/Slides/Drawings
                      are exported (text, csv, text, png by default).
  refresh             Force a token refresh and verify auth.
  config              View or pin the default profile.
  help                Show this help.

ls options:
  --name <text>       Name contains (whole Drive unless a folder is given)
  --search <text>     Full-text search (whole Drive unless a folder is given)
  --type file|folder  Only files or only folders
  --shared            Shared with me
  --query <q>         Raw Drive query; replaces the filters above
  --max-results <n>   Page size (default 100, max 1000)
  --all               Follow every page
  --pretty

get options:
  --out <file>        Write to a file instead of stdout
  --force             Overwrite an existing --out file (default: exit 15)
  --export-mime <t>   Export format for Google-native files (e.g. application/pdf)

Drive has no paths: address files by id (from ls/show). Shared drives are
not included.

Examples:
  owa-gdrive ls --pretty
  owa-gdrive ls 1AbC... --type file
  owa-gdrive ls --name budget --pretty
  owa-gdrive show 1AbC... --pretty
  owa-gdrive get 1AbC... --out notes.txt
  owa-gdrive get 1AbC... --export-mime application/pdf --out doc.pdf
""")
    print(schema_mod.MULTI_PROFILE_HELP)
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


def cmd_ls(args, config, token, base):
    q = {}
    folder = ''
    page_size = 100
    follow = pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag in ('--name', '--search', '--type', '--query'):
            value, args = _require_value(flag, args)
            q[{'--query': 'raw_query', '--type': 'file_type'}.get(flag, flag[2:])] = value
        elif flag == '--max-results':
            value, args = _require_value(flag, args)
            try:
                page_size = int(value)
            except ValueError as exc:
                raise UsageError('--max-results requires an integer') from exc
        elif flag == '--shared':
            q['shared'] = True
        elif flag == '--all':
            follow = True
        elif flag == '--pretty':
            pretty = True
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not folder:
            folder = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')
    if q.get('file_type', 'file') not in ('file', 'folder'):
        raise UsageError('--type must be file or folder')
    if not 1 <= page_size <= 1000:
        raise UsageError('--max-results must be between 1 and 1000')
    if not folder and not any(q.get(k) for k in ('name', 'search', 'shared', 'raw_query')):
        folder = 'root'  # a bare ls is My Drive's top level, not every file
    params = {
        'q': build_list_query(folder=folder, **q),
        'pageSize': page_size,
        'fields': LIST_FIELDS,
        'orderBy': 'folder,name_natural' if folder else 'modifiedTime desc',
    }
    if q.get('search'):
        params.pop('orderBy')  # Drive rejects orderBy with fullText queries
    files, next_token = api_mod.paginate(
        base, 'files', token, params, max_pages=None if follow else 1, debug=_debug_enabled(config),
    )
    rows = [normalize_file(f) for f in files]
    if pretty:
        print(format_files_pretty(rows))
        if next_token:
            print('\n(more: --all)')
    elif next_token and not follow:
        print(json.dumps({'files': rows, 'next_page_token': next_token}, ensure_ascii=False))
    else:
        print(json.dumps(rows, ensure_ascii=False))
    return 0


def _one_id(args, flags):
    file_id, opts = '', {}
    while args:
        flag, args = args[0], args[1:]
        if flag in ('--out', '--export-mime') and flag in flags:
            opts[flag[2:]], args = _require_value(flag, args)
        elif flag in flags:
            opts[flag[2:]] = True
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not file_id:
            file_id = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')
    if not file_id:
        raise UsageError('a file id is required')
    return file_id, opts


def _metadata(file_id, token, base, debug):
    return api_mod.api_get(base, f'files/{file_id}', token, params={'fields': FILE_FIELDS}, debug=debug)


def cmd_show(args, config, token, base):
    file_id, opts = _one_id(args, ('--pretty',))
    info = normalize_file(_metadata(file_id, token, base, _debug_enabled(config)))
    print(format_file_pretty(info) if opts.get('pretty') else json.dumps(info, ensure_ascii=False))
    return 0


def cmd_get(args, config, token, base):
    file_id, opts = _one_id(args, ('--out', '--force', '--export-mime'))
    out = opts.get('out')
    if out and not opts.get('force') and os.path.exists(out):
        raise ConflictError(f'local file already exists: {out} (pass --force to overwrite)')
    debug = _debug_enabled(config)
    # The mime type decides the endpoint: alt=media on a Google Doc is a 403.
    meta = _metadata(file_id, token, base, debug)
    if meta.get('mimeType') == FOLDER_MIME:
        raise UsageError(f'{file_id} is a folder; list it with: owa-gdrive ls {file_id}')
    try:
        export = resolve_export_mime(meta.get('mimeType'), opts.get('export-mime'))
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    if export:
        data = api_mod.api_get_bytes(base, f'files/{file_id}/export', token,
                                     params={'mimeType': export}, debug=debug)
    else:
        data = api_mod.api_get_bytes(base, f'files/{file_id}', token, params={'alt': 'media'}, debug=debug)
    if not out:
        sys.stdout.buffer.write(data)
        return 0
    with open(out, 'wb') as fh:
        fh.write(data)
    _info(f'wrote {len(data)} bytes to {out}' + (f' (exported as {export})' if export else ''))
    return 0


def cmd_refresh(args, config):
    if args:
        raise UsageError(f'Unknown flag: {args[0]}')
    token, base = auth_mod.setup_auth(config, debug=_debug_enabled(config))
    user = (api_mod.api_get(base, 'about', token, params={'fields': 'user'},
                            debug=_debug_enabled(config)) or {}).get('user') or {}
    _info(f"Authenticated as {user.get('displayName') or '?'} <{user.get('emailAddress') or '?'}>")
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


AUTHED_COMMANDS = {'ls': cmd_ls, 'show': cmd_show, 'get': cmd_get}

_PRETTY = schema_mod.flag('--pretty', summary='Human-readable output (default: JSON)')

COMMAND_SCHEMA = [
    schema_mod.command('ls', 'List a folder or search the Drive', auth=auth_mod.AUDIENCE, aliases=['list'], flags=[
        schema_mod.flag('<folder-id>', summary='Folder id (default: My Drive top level)'),
        schema_mod.flag('--name', value='<text>', summary='Name contains'),
        schema_mod.flag('--search', value='<text>', summary='Full-text search'),
        schema_mod.flag('--type', value='<file|folder>', summary='Only files or only folders'),
        schema_mod.flag('--shared', summary='Shared with me'),
        schema_mod.flag('--query', value='<q>', summary='Raw Drive query (replaces the filters)'),
        schema_mod.flag('--max-results', value='<n>', summary='Page size (default 100, max 1000)'),
        schema_mod.flag('--all', summary='Follow every page'),
        _PRETTY,
    ]),
    schema_mod.command('show', 'Show file metadata', auth=auth_mod.AUDIENCE, flags=[
        schema_mod.flag('<id>', summary='File id', required=True), _PRETTY,
    ]),
    schema_mod.command('get', 'Download (or export) a file', auth=auth_mod.AUDIENCE, output='bytes',
                       aliases=['download'], flags=[
        schema_mod.flag('<id>', summary='File id', required=True),
        schema_mod.flag('--out', value='<file>', summary='Write to a file instead of stdout'),
        schema_mod.flag('--force', summary='Overwrite an existing --out file (default: exit 15)'),
        schema_mod.flag('--export-mime', value='<type>', summary='Export format for Google-native files'),
    ]),
    schema_mod.command('refresh', 'Force a token refresh', auth=auth_mod.AUDIENCE),
    schema_mod.command('config', 'View or update configuration', mutates=True, flags=[
        schema_mod.flag('--profile', value='<alias>', summary='Pin a default owa-piggy profile alias'),
    ]),
]


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-gdrive', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled
    if not argv or argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] in ('--version', '-v'):
        print(f'owa-gdrive {__version__}')
        return 0

    argv, debug_flag, profile_override = mode_mod.strip_global_flags(argv)
    if not argv:
        print_help()
        return 0
    cmd, rest = schema_mod.resolve_alias(argv[0], COMMAND_SCHEMA), argv[1:]
    help_rc = schema_mod.maybe_emit_subcommand_help(cmd, rest, tool='owa-gdrive', commands=COMMAND_SCHEMA)
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
        raise UsageError(f"Unknown command: {cmd}. Run 'owa-gdrive help' for usage.")
    schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)
    token, base = auth_mod.setup_auth(config, debug=_debug_enabled(config))
    return AUTHED_COMMANDS[cmd](rest, config, token, base)


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-gdrive',
        sys.argv[1:] if argv is None else argv,
        _main,
        binary_stdout_commands=('get',),
        commands=COMMAND_SCHEMA,
        service=auth_mod.SERVICE,
    )
