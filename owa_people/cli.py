"""Argument parsing and dispatch for `owa-people`.

JSON on stdout, logs on stderr, --pretty for humans. Mirrors the
flat-dispatch style of owa-cal: each cmd_* parses its own flags.
"""
import json
import os
import sys

from owa_core import schema as schema_mod

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from .api import build_query
from .format import format_people_pretty, format_person_pretty
from .people import normalize_person


def _error(msg):
    print(f'ERROR: {msg}', file=sys.stderr)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('PEOPLE_DEBUG') == '1'


def _require_value(flag, args):
    if not args:
        _error(f'{flag} requires a value'); sys.exit(1)
    return args[0], args[1:]


def _require_int(flag, args):
    v, args = _require_value(flag, args)
    try:
        return int(v), args
    except ValueError:
        _error(f'{flag} requires an integer, got: {v}'); sys.exit(1)


def print_help():
    print("""owa-people - People/contacts CLI for Outlook / Microsoft 365

Usage: owa-people <command> [options]

Global options:
  --debug, --verbose  Print HTTP requests and response bodies on errors
                      (also: PEOPLE_DEBUG=1)
  --profile <alias>   Forward to owa-piggy as --profile <alias> for
                      this invocation. Overrides owa_piggy_profile in
                      the config file.

Commands:
  find <query>        Search people you've recently interacted with
                      (relevance-ranked: /me/people).
  show <id-or-email>  Show full details for one person.
  directory <query>   Search the company directory (/users).
  me                  Show the authenticated user (/me).
  contacts            List your personal contacts (/me/contacts).
  refresh             Force a token refresh and verify auth.
  config              View or update configuration.
  help                Show this help.

Common options:
  --pretty            Human-readable output (default: JSON).
  --limit <n>         Max results (default: 25, max 100).

Examples:
  owa-people find "vibeke" --pretty
  owa-people show vtv@une.no
  owa-people directory "norconsult" --limit 50 --pretty
  owa-people me --pretty
  owa-people --profile crayon find "ole kristian"
""")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_find(args, config, access_token, api_base):
    pretty = False
    limit = 25
    query_parts = []
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--limit':
            limit, args = _require_int(flag, args)
        elif flag.startswith('-'):
            _error(f'Unknown flag: {flag}'); sys.exit(1)
        else:
            query_parts.append(flag)
    query = ' '.join(query_parts).strip()
    if not query:
        _error('find requires a search query')
        return 1
    qs = build_query({
        '$search': f'"{query}"',
        '$top': max(1, min(limit, 100)),
    })
    endpoint = f'me/people?{qs}'
    payload = api_mod.api_get(
        api_base, endpoint, access_token,
        extra_headers={'ConsistencyLevel': 'eventual'},
        debug=_debug_enabled(config),
    )
    if payload is None:
        return 1
    items = payload.get('value') or []
    people = [normalize_person(i, 'people') for i in items]
    if pretty:
        print(format_people_pretty(people))
    else:
        print(json.dumps(people))
    return 0


def cmd_directory(args, config, access_token, api_base):
    pretty = False
    limit = 25
    query_parts = []
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--limit':
            limit, args = _require_int(flag, args)
        elif flag.startswith('-'):
            _error(f'Unknown flag: {flag}'); sys.exit(1)
        else:
            query_parts.append(flag)
    query = ' '.join(query_parts).strip()
    if not query:
        _error('directory requires a search query')
        return 1
    # /users $search needs ConsistencyLevel=eventual and quoted property:value pairs
    search = (
        f'"displayName:{query}" OR "mail:{query}" '
        f'OR "userPrincipalName:{query}"'
    )
    qs = build_query({
        '$search': search,
        '$top': max(1, min(limit, 100)),
        '$select': (
            'id,displayName,mail,userPrincipalName,jobTitle,department,'
            'companyName,officeLocation,mobilePhone,businessPhones'
        ),
    })
    endpoint = f'users?{qs}'
    payload = api_mod.api_get(
        api_base, endpoint, access_token,
        extra_headers={'ConsistencyLevel': 'eventual'},
        debug=_debug_enabled(config),
    )
    if payload is None:
        return 1
    items = payload.get('value') or []
    people = [normalize_person(i, 'directory') for i in items]
    if pretty:
        print(format_people_pretty(people))
    else:
        print(json.dumps(people))
    return 0


def cmd_show(args, config, access_token, api_base):
    pretty = False
    target = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag.startswith('-'):
            _error(f'Unknown flag: {flag}'); sys.exit(1)
        elif not target:
            target = flag
        else:
            _error(f'Unexpected argument: {flag}'); sys.exit(1)
    if not target:
        _error('show requires an id or email')
        return 1
    # Heuristic: looks like an email -> /users/<email>; otherwise treat
    # as a Graph object id.
    endpoint = f'users/{target}'
    payload = api_mod.api_get(
        api_base, endpoint, access_token,
        debug=_debug_enabled(config),
    )
    if payload is None:
        return 1
    person = normalize_person(payload, 'directory')
    if pretty:
        print(format_person_pretty(person))
    else:
        print(json.dumps(person))
    return 0


def cmd_me(args, config, access_token, api_base):
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)
    payload = api_mod.api_get(
        api_base, 'me', access_token,
        debug=_debug_enabled(config),
    )
    if payload is None:
        return 1
    person = normalize_person(payload, 'directory')
    if pretty:
        print(format_person_pretty(person))
    else:
        print(json.dumps(person))
    return 0


def cmd_contacts(args, config, access_token, api_base):
    pretty = False
    limit = 50
    search = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--limit':
            limit, args = _require_int(flag, args)
        elif flag == '--search':
            search, args = _require_value(flag, args)
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)
    params = {}
    params['$top'] = str(max(1, min(limit, 100)))
    if search:
        params['$search'] = f'"{search}"'
    qs = build_query(params)
    endpoint = f'me/contacts?{qs}'
    extra = {'ConsistencyLevel': 'eventual'} if search else None
    payload = api_mod.api_get(
        api_base, endpoint, access_token,
        extra_headers=extra,
        debug=_debug_enabled(config),
    )
    if payload is None:
        return 1
    items = payload.get('value') or []
    people = [normalize_person(i, 'contacts') for i in items]
    if pretty:
        print(format_people_pretty(people))
    else:
        print(json.dumps(people))
    return 0


def cmd_config(args, config):
    profile = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--profile':
            profile, args = _require_value(flag, args)
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)

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
        _error(f'Unknown flag: {args[0]}'); sys.exit(1)
    _info('Refreshing token...')
    access = auth_mod.do_token_refresh(config, debug=_debug_enabled(config))
    if not access:
        _error('Token refresh failed.')
        return 1
    me = api_mod.api_get(
        'https://graph.microsoft.com/v1.0', 'me', access,
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

AUTHED_COMMANDS = {'find', 'show', 'directory', 'me', 'contacts'}


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


COMMAND_SCHEMA = [
    schema_mod.command('find', 'Search recent people', auth='graph'),
    schema_mod.command('show', 'Show one person', auth='graph'),
    schema_mod.command('directory', 'Search company directory', auth='graph'),
    schema_mod.command('me', 'Show authenticated user', auth='graph'),
    schema_mod.command('contacts', 'List personal contacts', auth='graph'),
    schema_mod.command('refresh', 'Force a token refresh', auth='graph'),
    schema_mod.command('config', 'View or update configuration'),
]


def main():
    argv = sys.argv[1:]
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-people', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled

    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] == '--version':
        print(f'owa-people {__version__}')
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
        _error(f"Unknown command: {cmd}. Run 'owa-people help' for usage.")
        return 1

    access_token, api_base = auth_mod.setup_auth(
        config, debug=_debug_enabled(config),
    )

    if cmd == 'find':
        return cmd_find(rest, config, access_token, api_base)
    if cmd == 'show':
        return cmd_show(rest, config, access_token, api_base)
    if cmd == 'directory':
        return cmd_directory(rest, config, access_token, api_base)
    if cmd == 'me':
        return cmd_me(rest, config, access_token, api_base)
    if cmd == 'contacts':
        return cmd_contacts(rest, config, access_token, api_base)

    return 1
