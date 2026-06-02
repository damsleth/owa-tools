"""Argument parsing and dispatch for the `owa-sites` command.

owa-sites is pipe-friendly: JSON on stdout, logs on stderr. --pretty switches
stdout to a human-readable view. It reads the SharePoint REST API on the
per-tenant `*.sharepoint.com` host, using a SharePoint-resource token minted via
owa-piggy's `--scope` override (the shared graph token lacks `Sites.Read.All`,
so the Graph `/sites` API 403s; SharePoint REST is the working door). See auth.py.

Read-only v1. File download and upload (binary / mutating) are deferred - see
AGENTS.md.

Subcommands are parsed manually (no argparse subparsers) to match the rest of
the suite; each cmd_* fn owns its own flag loop.
"""
import json
import os
import sys

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core.errors import OwaError, UsageError, emit_error, emit_message

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from . import sites as sites_mod
from .format import (
    format_files_pretty,
    format_items_pretty,
    format_lists_pretty,
    format_search_pretty,
    format_web_pretty,
)


def _error(msg):
    emit_message(msg)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('SITES_DEBUG') == '1'


def _command_name(argv):
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ('--debug', '--verbose'):
            i += 1
            continue
        if arg == '--profile':
            i += 2
            continue
        return arg
    return ''


def _require_value(flag, args):
    if not args:
        raise UsageError(f'{flag} requires a value')
    return args[0], args[1:]


def _require_int(flag, args):
    v, args = _require_value(flag, args)
    try:
        return int(v), args
    except ValueError:
        raise UsageError(f'{flag} requires an integer, got: {v}')


def _resolve_site(site, config):
    return site or (config.get('default_site') or '')


def print_help():
    print("""owa-sites - SharePoint CLI for Microsoft 365

Usage: owa-sites <command> [options]

Global options:
  --debug, --verbose  Print HTTP requests and response bodies on errors
                      (also: SITES_DEBUG=1)
  --profile <alias>   owa-piggy profile alias for this invocation.

Commands:
  site                Show a site's web (title, url)
  lists               List a site's lists / document libraries
  items               List items in a list (--list <title>)
  files               List files in a folder (--path <server-relative>)
  search              Tenant search for sites and content (--q <text>)
  config              View or update configuration
  refresh             Force a token refresh and verify SharePoint access
  help                Show this help

Site addressing:
  --site <addr>       Bare name (`owa-casa`), an explicit path (`sites/owa-casa`,
                      `teams/x`), or omitted for the tenant root site. The `site`
                      command also accepts the address as a bare positional.

Items options:
  --list <title>      List title (required)
  --select <f1,f2>    Restrict returned fields
  --top <n>           Page size

Files options:
  --path <srv-rel>    Server-relative folder, e.g. /sites/owa-casa/Shared Documents

Search options:
  --q <text>          Query text (required)
  --limit <n>         Row limit (default 20, cap 200)

Config options:
  --profile <alias>   Pin a default owa-piggy profile alias
  --host <host>       Pin the tenant SharePoint host (skips auto-discovery)
  --site <addr>       Pin a default site

Auth:
  owa-sites mints a SharePoint-resource token via owa-piggy (`--scope
  https://<tenant>.sharepoint.com/.default`), carrying Sites.FullControl.All.
  The host is auto-discovered from the tenant's initial domain unless pinned.

Examples:
  owa-sites site owa-casa --pretty
  owa-sites lists --site owa-casa --pretty
  owa-sites items --site owa-casa --list Documents
  owa-sites files --site owa-casa --path "/sites/owa-casa/Shared Documents"
  owa-sites search --q "quarterly report" --pretty""")
    print()
    print(schema_mod.MULTI_PROFILE_HELP)
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_site(args, config, access_token, base):
    site, args = schema_mod.pop_positional_id(args)
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--site':
            site, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    site = _resolve_site(site, config)
    debug = _debug_enabled(config)
    data = api_mod.sp_get(base, sites_mod.web_endpoint(site), access_token, debug=debug)
    if data is None:
        return 1
    web = sites_mod.normalize_web(data)
    print(format_web_pretty(web) if pretty else json.dumps(web))
    return 0


def cmd_lists(args, config, access_token, base):
    site = ''
    pretty = include_hidden = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--site':
            site, args = _require_value(flag, args)
        elif flag == '--all-lists':
            include_hidden = True
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    site = _resolve_site(site, config)
    debug = _debug_enabled(config)
    data = api_mod.paginate_sp(base, sites_mod.lists_endpoint(site), access_token, debug=debug)
    if data is None:
        return 1
    rows = sites_mod.normalize_lists(data, include_hidden=include_hidden)
    print(format_lists_pretty(rows) if pretty else json.dumps(rows))
    return 0


def cmd_items(args, config, access_token, base):
    site = list_title = select = ''
    top = 0
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--site':
            site, args = _require_value(flag, args)
        elif flag == '--list':
            list_title, args = _require_value(flag, args)
        elif flag == '--select':
            select, args = _require_value(flag, args)
        elif flag == '--top':
            top, args = _require_int(flag, args)
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if not list_title:
        raise UsageError('--list is required')
    site = _resolve_site(site, config)
    debug = _debug_enabled(config)
    endpoint = sites_mod.list_items_endpoint(site, list_title, select=select, top=top)
    data = api_mod.paginate_sp(base, endpoint, access_token, debug=debug)
    if data is None:
        return 1
    rows = sites_mod.normalize_items(data)
    print(format_items_pretty(rows) if pretty else json.dumps(rows))
    return 0


def cmd_files(args, config, access_token, base):
    site = path = ''
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--site':
            site, args = _require_value(flag, args)
        elif flag == '--path':
            path, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if not path:
        raise UsageError('--path is required (server-relative folder)')
    site = _resolve_site(site, config)
    debug = _debug_enabled(config)
    data = api_mod.paginate_sp(
        base, sites_mod.folder_files_endpoint(site, path), access_token, debug=debug,
    )
    if data is None:
        return 1
    rows = sites_mod.normalize_files(data)
    print(format_files_pretty(rows) if pretty else json.dumps(rows))
    return 0


def cmd_search(args, config, access_token, base):
    query = ''
    rowlimit = 20
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--q':
            query, args = _require_value(flag, args)
        elif flag == '--limit':
            rowlimit, args = _require_int(flag, args)
            rowlimit = max(1, min(rowlimit, 200))
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if not query:
        raise UsageError('--q is required')
    debug = _debug_enabled(config)
    data = api_mod.sp_get(
        base, sites_mod.search_endpoint(query, rowlimit=rowlimit), access_token, debug=debug,
    )
    if data is None:
        return 1
    rows = sites_mod.flatten_search_rows(data)
    print(format_search_pretty(rows) if pretty else json.dumps(rows))
    return 0


def cmd_config(args, config):
    profile = host = site = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--profile':
            profile, args = _require_value(flag, args)
        elif flag == '--host':
            host, args = _require_value(flag, args)
        elif flag == '--site':
            site, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')

    changed = False
    if profile:
        config_mod.config_set('owa_piggy_profile', profile)
        _info(f'default profile saved: {profile}')
        changed = True
    if host:
        config_mod.config_set('sharepoint_host', host)
        _info(f'sharepoint_host saved: {host}')
        changed = True
    if site:
        config_mod.config_set('default_site', site)
        _info(f'default site saved: {site}')
        changed = True
    if changed:
        return 0

    _info(f'Config file: {config_mod.CONFIG_PATH}')
    if config.get('owa_piggy_profile'):
        _info(f"  owa_piggy_profile={config.get('owa_piggy_profile')}")
    else:
        _info('  owa_piggy_profile=(not set - owa-piggy picks its default)')
    _info(f"  sharepoint_host={config.get('sharepoint_host') or '(not set - auto-discovered)'}")
    _info(f"  default_site={config.get('default_site') or '(not set - root site)'}")
    return 0


def cmd_refresh(args, config):
    if args:
        raise UsageError(f'Unknown flag: {args[0]}')
    _info('Refreshing token...')
    debug = _debug_enabled(config)
    try:
        access, base = auth_mod.setup_auth(config, debug=debug)
    except OwaError as error:
        return emit_error(error)
    web = api_mod.sp_get(
        base, sites_mod.api_endpoint('', 'web?$select=Title,Url'), access, debug=debug,
    )
    if not isinstance(web, dict):
        _error('Auth verification failed.')
        return 1
    if web.get('Title'):
        _info(f"Connected to {base} (root web: {web['Title']})")
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

AUTHED_COMMANDS = {'site', 'lists', 'items', 'files', 'search'}

_SITE_FLAGS = [
    schema_mod.flag('--site', value='<addr>', summary='Site address (flag or positional); default: root'),
    schema_mod.flag('--pretty', summary='Human-readable output (default: JSON)'),
]

_LISTS_FLAGS = [
    schema_mod.flag('--site', value='<addr>', summary='Site address (default: root)'),
    schema_mod.flag('--all-lists', summary='Include hidden/system lists'),
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
]

_ITEMS_FLAGS = [
    schema_mod.flag('--list', value='<title>', summary='List title', required=True),
    schema_mod.flag('--site', value='<addr>', summary='Site address (default: root)'),
    schema_mod.flag('--select', value='<f1,f2>', summary='Restrict returned fields'),
    schema_mod.flag('--top', value='<n>', summary='Page size'),
    schema_mod.flag('--pretty', summary='Human-readable output (default: JSON)'),
]

_FILES_FLAGS = [
    schema_mod.flag('--path', value='<srv-rel>', summary='Server-relative folder', required=True),
    schema_mod.flag('--site', value='<addr>', summary='Site address (default: root)'),
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
]

_SEARCH_FLAGS = [
    schema_mod.flag('--q', value='<text>', summary='Query text', required=True),
    schema_mod.flag('--limit', value='<n>', summary='Row limit (default 20, cap 200)'),
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
]

_CONFIG_FLAGS = [
    schema_mod.flag('--profile', value='<alias>', summary='Pin a default owa-piggy profile alias'),
    schema_mod.flag('--host', value='<host>', summary='Pin the tenant SharePoint host'),
    schema_mod.flag('--site', value='<addr>', summary='Pin a default site'),
]

COMMAND_SCHEMA = [
    schema_mod.command('site', 'Show a site web', auth='graph', flags=_SITE_FLAGS),
    schema_mod.command('lists', 'List a site\'s lists / libraries', auth='graph', flags=_LISTS_FLAGS),
    schema_mod.command('items', 'List items in a list', auth='graph', flags=_ITEMS_FLAGS),
    schema_mod.command('files', 'List files in a folder', auth='graph', flags=_FILES_FLAGS),
    schema_mod.command('search', 'Tenant search for sites and content', auth='graph', flags=_SEARCH_FLAGS),
    schema_mod.command('refresh', 'Force a token refresh', auth='graph'),
    schema_mod.command('config', 'View or update configuration', mutates=True, flags=_CONFIG_FLAGS),
]


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-sites', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled

    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] == '--version':
        print(f'owa-sites {__version__}')
        return 0

    debug_flag = False
    profile_override = ''
    # Strip global flags (--debug/--verbose, --profile) from anywhere in argv.
    # Exception: on `owa-sites config`, --profile is a subcommand flag.
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

    help_rc = schema_mod.maybe_emit_subcommand_help(
        cmd, rest, tool='owa-sites', commands=COMMAND_SCHEMA,
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
        raise UsageError(f"Unknown command: {cmd}. Run 'owa-sites help' for usage.")

    schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)

    access_token, base = auth_mod.setup_auth(config, debug=_debug_enabled(config))

    if cmd == 'site':
        return cmd_site(rest, config, access_token, base)
    if cmd == 'lists':
        return cmd_lists(rest, config, access_token, base)
    if cmd == 'items':
        return cmd_items(rest, config, access_token, base)
    if cmd == 'files':
        return cmd_files(rest, config, access_token, base)
    if cmd == 'search':
        return cmd_search(rest, config, access_token, base)

    # Unreachable: AUTHED_COMMANDS guarded above.
    return 1


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-sites', sys.argv[1:] if argv is None else argv, _main,
    )
