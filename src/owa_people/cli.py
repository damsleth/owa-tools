"""Argument parsing and dispatch for `owa-people`.

JSON on stdout, logs on stderr, --pretty for humans. Mirrors the
flat-dispatch style of owa-cal: each cmd_* parses its own flags.
"""
import json
import os
import sys
import urllib.parse

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core import tty as tty_mod
from owa_core.errors import UsageError, _require_value, emit_error, emit_message

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from .api import build_query
from .format import format_groups_pretty, format_people_pretty, format_person_pretty
from .people import normalize_group, normalize_person


def _error(msg):
    emit_message(msg)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('PEOPLE_DEBUG') == '1'


def _require_int(flag, args):
    v, args = _require_value(flag, args)
    try:
        return int(v), args
    except ValueError:
        raise UsageError(f'{flag} requires an integer, got: {v}')


def _quote_id(target):
    # Graph addresses /users/{upn-or-id}; UPNs are safe but a paranoid
    # quote keeps odd characters from breaking the path.
    return urllib.parse.quote(target, safe='@.')


def print_help():
    print("""owa-people - People/contacts CLI for Outlook / Microsoft 365

Usage: owa-people <command> [options]
       owa-people <query>          (shorthand for: owa-people find <query>)

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
  manager <id>        Show a user's manager (/users/<id>/manager).
  direct-reports <id> List a user's direct reports.
  org-chart <id>      Walk the management chain up and reports down.
  photo <id>          Fetch a user's photo as binary on stdout.
  groups [<id>]       List a user's group memberships (/memberOf).
  contacts            List your personal contacts (/me/contacts).
  contact-create      Create a personal contact (/me/contacts).
  contact-update <id> Update a personal contact.
  contact-delete <id> Delete a personal contact.
  refresh             Force a token refresh and verify auth.
  config              View or update configuration.
  help                Show this help.

Common options:
  --pretty            Human-readable output (default: JSON).
  --limit, --top <n>  Max results per page (default: 25, max 100).
  --select <props>    OData $select passthrough (comma-separated).
  --filter <expr>     OData $filter passthrough.
  --all               (directory/contacts/groups/direct-reports) Follow
                      @odata.nextLink until exhausted. --limit still controls
                      page size. Not available on find (/me/people no page).

Examples:
  owa-people find "vibeke" --pretty
  owa-people show vtv@une.no
  owa-people directory "norconsult" --limit 50 --pretty
  owa-people manager vtv@une.no --pretty
  owa-people org-chart vtv@une.no --depth 2
  owa-people photo vtv@une.no > avatar.jpg
  owa-people groups --pretty
  owa-people contact-create --name "Ada" --email ada@ex.com
  owa-people --profile crayon find "ole kristian"
""")
    print()
    print(schema_mod.MULTI_PROFILE_HELP)
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_find(args, config, access_token, api_base):
    pretty = False
    limit = 25
    select = filter_expr = ''
    query_parts = []
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag in ('--limit', '--top'):
            limit, args = _require_int(flag, args)
        elif flag == '--select':
            select, args = _require_value(flag, args)
        elif flag == '--filter':
            filter_expr, args = _require_value(flag, args)
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        else:
            query_parts.append(flag)
    query = ' '.join(query_parts).strip()
    if not query:
        raise UsageError('find requires a search query')
    params = {
        '$search': f'"{query}"',
        '$top': max(1, min(limit, 100)),
    }
    if select:
        params['$select'] = select
    if filter_expr:
        params['$filter'] = filter_expr
    qs = build_query(params)
    # No --all here: /me/people is relevance-ranked and uses client-driven
    # $top/$skip paging with no @odata.nextLink (and $skip is unsupported
    # alongside $search), so there is no server page chain to follow.
    endpoint = f'me/people?{qs}'
    headers = {'ConsistencyLevel': 'eventual'}
    payload = api_mod.api_get(
        api_base, endpoint, access_token,
        extra_headers=headers,
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
    all_pages = False
    limit = 25
    select = filter_expr = ''
    query_parts = []
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--all':
            all_pages = True
        elif flag in ('--limit', '--top'):
            limit, args = _require_int(flag, args)
        elif flag == '--select':
            select, args = _require_value(flag, args)
        elif flag == '--filter':
            filter_expr, args = _require_value(flag, args)
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        else:
            query_parts.append(flag)
    query = ' '.join(query_parts).strip()
    if not query:
        raise UsageError('directory requires a search query')
    # /users $search needs ConsistencyLevel=eventual and quoted property:value pairs
    search = (
        f'"displayName:{query}" OR "mail:{query}" '
        f'OR "userPrincipalName:{query}"'
    )
    params = {
        '$search': search,
        '$top': max(1, min(limit, 100)),
        '$select': select or (
            'id,displayName,mail,userPrincipalName,jobTitle,department,'
            'companyName,officeLocation,mobilePhone,businessPhones'
        ),
    }
    if filter_expr:
        params['$filter'] = filter_expr
    qs = build_query(params)
    endpoint = f'users?{qs}'
    headers = {'ConsistencyLevel': 'eventual'}
    if all_pages:
        items = api_mod.paginate_all(
            api_base, endpoint, access_token,
            extra_headers=headers, debug=_debug_enabled(config),
        )
        if items is None:
            return 1
        people = [normalize_person(i, 'directory') for i in items]
        if pretty:
            print(format_people_pretty(people))
        else:
            print(json.dumps(people))
        return 0
    payload = api_mod.api_get(
        api_base, endpoint, access_token,
        extra_headers=headers,
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
            raise UsageError(f'Unknown flag: {flag}')
        elif not target:
            target = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')
    if not target:
        raise UsageError('show requires an id or email')
    # Graph /users accepts both a UPN (email) and an object id at the same
    # endpoint, so no branching is needed.
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
            raise UsageError(f'Unknown flag: {flag}')
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


def _pop_target(args, default='me'):
    """Parse a leading positional id/email plus --pretty for the org
    commands. Returns (target, pretty, remaining_args)."""
    target = ''
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not target:
            target = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')
    return (target or default), pretty


def _user_path(target):
    return 'me' if target == 'me' else f'users/{_quote_id(target)}'


def cmd_manager(args, config, access_token, api_base):
    target, pretty = _pop_target(args)
    endpoint = f'{_user_path(target)}/manager'
    payload = api_mod.api_get(
        api_base, endpoint, access_token, debug=_debug_enabled(config),
    )
    if payload is None:
        return 1
    person = normalize_person(payload, 'directory')
    if pretty:
        print(format_person_pretty(person))
    else:
        print(json.dumps(person))
    return 0


def cmd_direct_reports(args, config, access_token, api_base):
    target = ''
    pretty = all_pages = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--all':
            all_pages = True
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not target:
            target = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')
    target = target or 'me'
    endpoint = f'{_user_path(target)}/directReports'
    debug = _debug_enabled(config)
    if all_pages:
        items = api_mod.paginate_all(api_base, endpoint, access_token, debug=debug)
        if items is None:
            return 1
    else:
        payload = api_mod.api_get(api_base, endpoint, access_token, debug=debug)
        if payload is None:
            return 1
        items = payload.get('value') or []
    people = [normalize_person(i, 'directory') for i in items]
    if pretty:
        print(format_people_pretty(people))
    else:
        print(json.dumps(people))
    return 0


def cmd_org_chart(args, config, access_token, api_base):
    target = ''
    pretty = False
    depth = 1
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--depth':
            depth, args = _require_int(flag, args)
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not target:
            target = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')
    target = target or 'me'
    depth = max(1, min(depth, 3))
    debug = _debug_enabled(config)

    base = api_mod.api_get(api_base, _user_path(target), access_token, debug=debug)
    if base is None:
        return 1
    person = normalize_person(base, 'directory')
    person_id = base.get('id') or target

    # Walk managers up to `depth` levels. A missing manager is a 404, which
    # api_get surfaces as None - treat as "top of chain" and stop.
    chain = []
    current = person_id
    for _ in range(depth):
        mgr = api_mod.api_get(
            api_base, f'users/{_quote_id(str(current))}/manager', access_token, debug=debug,
        )
        if not mgr:
            break
        chain.append(normalize_person(mgr, 'directory'))
        current = mgr.get('id')
        if not current:
            break

    reports_payload = api_mod.api_get(
        api_base, f'users/{_quote_id(str(person_id))}/directReports', access_token, debug=debug,
    )
    reports = [
        normalize_person(i, 'directory')
        for i in ((reports_payload or {}).get('value') or [])
    ]

    chart = {'person': person, 'managers': chain, 'directReports': reports}
    if pretty:
        lines = []
        for m in reversed(chain):
            lines.append(f"^ {m.get('displayName')} <{m.get('email')}>")
        lines.append(f"* {person.get('displayName')} <{person.get('email')}>")
        for r in reports:
            lines.append(f"  - {r.get('displayName')} <{r.get('email')}>")
        print('\n'.join(lines))
    else:
        print(json.dumps(chart))
    return 0


def cmd_photo(args, config, access_token, api_base):
    target = ''
    out_path = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--out':
            out_path, args = _require_value(flag, args)
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not target:
            target = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')
    target = target or 'me'
    endpoint = f'{_user_path(target)}/photo/$value'
    content = api_mod.api_get_binary(
        api_base, endpoint, access_token, debug=_debug_enabled(config),
    )
    if content is None:
        return 1
    if out_path:
        with open(out_path, 'wb') as fh:
            fh.write(content)
        _info(f'wrote {len(content)} bytes to {out_path}')
    else:
        sys.stdout.buffer.write(content)
    return 0


def cmd_groups(args, config, access_token, api_base):
    target = ''
    pretty = all_pages = False
    limit = 50
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--all':
            all_pages = True
        elif flag in ('--limit', '--top'):
            limit, args = _require_int(flag, args)
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not target:
            target = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')
    target = target or 'me'
    qs = build_query({'$top': max(1, min(limit, 100))})
    endpoint = f'{_user_path(target)}/memberOf?{qs}'
    debug = _debug_enabled(config)
    if all_pages:
        items = api_mod.paginate_all(api_base, endpoint, access_token, debug=debug)
        if items is None:
            return 1
    else:
        payload = api_mod.api_get(api_base, endpoint, access_token, debug=debug)
        if payload is None:
            return 1
        items = payload.get('value') or []
    groups = [normalize_group(i) for i in items]
    if pretty:
        print(format_groups_pretty(groups))
    else:
        print(json.dumps(groups))
    return 0


# --- personal contact CRUD (/me/contacts) ---------------------------------

def _build_contact_body(name, given, surname, email, mobile, company, title):
    body = {}
    if name:
        body['displayName'] = name
    if given:
        body['givenName'] = given
    if surname:
        body['surname'] = surname
    if email:
        body['emailAddresses'] = [{'address': email, 'name': name or email}]
    if mobile:
        body['mobilePhone'] = mobile
    if company:
        body['companyName'] = company
    if title:
        body['jobTitle'] = title
    return body


def _parse_contact_flags(args):
    fields = {'name': '', 'given': '', 'surname': '', 'email': '',
              'mobile': '', 'company': '', 'title': ''}
    flagmap = {
        '--name': 'name', '--given': 'given', '--surname': 'surname',
        '--email': 'email', '--mobile': 'mobile', '--company': 'company',
        '--title': 'title',
    }
    rest = []
    while args:
        flag, args = args[0], args[1:]
        if flag in flagmap:
            fields[flagmap[flag]], args = _require_value(flag, args)
        else:
            rest.append(flag)
    return fields, rest


def cmd_contact_create(args, config, access_token, api_base):
    fields, rest = _parse_contact_flags(args)
    if rest:
        raise UsageError(f'Unknown flag: {rest[0]}')
    if not (fields['name'] or fields['given'] or fields['surname'] or fields['email']):
        raise UsageError('contact-create requires at least --name or --email')
    body = _build_contact_body(
        fields['name'], fields['given'], fields['surname'], fields['email'],
        fields['mobile'], fields['company'], fields['title'],
    )
    result = api_mod.api_request(
        'POST', api_base, 'me/contacts', access_token,
        body=body, debug=_debug_enabled(config),
    )
    if not result:
        return 1
    print(json.dumps(normalize_person(result, 'contacts')))
    return 0


def cmd_contact_update(args, config, access_token, api_base):
    contact_id, args = schema_mod.pop_positional_id(args)
    fields, rest = _parse_contact_flags(args)
    extra = []
    for flag in rest:
        if flag == '--id':
            raise UsageError('--id requires a value')
        extra.append(flag)
    if extra:
        raise UsageError(f'Unknown flag: {extra[0]}')
    if not contact_id:
        raise UsageError('contact-update requires a contact id')
    body = _build_contact_body(
        fields['name'], fields['given'], fields['surname'], fields['email'],
        fields['mobile'], fields['company'], fields['title'],
    )
    if not body:
        _error('contact-update requires at least one field to change')
        return 1
    endpoint = f'me/contacts/{_quote_id(contact_id)}'
    result = api_mod.api_request(
        'PATCH', api_base, endpoint, access_token,
        body=body, debug=_debug_enabled(config),
    )
    if not result:
        return 1
    print(json.dumps(normalize_person(result, 'contacts')))
    return 0


def cmd_contact_delete(args, config, access_token, api_base):
    contact_id, args = schema_mod.pop_positional_id(args)
    confirm = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            contact_id, args = _require_value(flag, args)
        elif flag == '--confirm':
            confirm = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if not contact_id:
        raise UsageError('contact-delete requires a contact id')
    debug = _debug_enabled(config)
    endpoint = f'me/contacts/{_quote_id(contact_id)}'
    if not confirm:
        try:
            tty_mod.require_confirm_or_tty(action='delete contact')
        except UsageError as error:
            return emit_error(error)
        existing = api_mod.api_get(api_base, endpoint, access_token, debug=debug)
        if not existing:
            return 1
        person = normalize_person(existing, 'contacts')
        if not tty_mod.confirm(
            f"\033[33mDelete contact '{person.get('displayName') or person.get('email')}'? (y/N): \033[0m"
        ):
            _info('Aborted.')
            return 0
    result = api_mod.api_request('DELETE', api_base, endpoint, access_token, debug=debug)
    if result is None:
        return 1
    _info('Deleted.')
    return 0


def cmd_contacts(args, config, access_token, api_base):
    pretty = False
    all_pages = False
    limit = 50
    search = select = filter_expr = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--all':
            all_pages = True
        elif flag in ('--limit', '--top'):
            limit, args = _require_int(flag, args)
        elif flag == '--search':
            search, args = _require_value(flag, args)
        elif flag == '--select':
            select, args = _require_value(flag, args)
        elif flag == '--filter':
            filter_expr, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')
    params = {}
    params['$top'] = str(max(1, min(limit, 100)))
    if search:
        params['$search'] = f'"{search}"'
    if select:
        params['$select'] = select
    if filter_expr:
        params['$filter'] = filter_expr
    qs = build_query(params)
    endpoint = f'me/contacts?{qs}'
    extra = {'ConsistencyLevel': 'eventual'} if search else None
    if all_pages:
        items = api_mod.paginate_all(
            api_base, endpoint, access_token,
            extra_headers=extra, debug=_debug_enabled(config),
        )
        if items is None:
            return 1
        people = [normalize_person(i, 'contacts') for i in items]
        if pretty:
            print(format_people_pretty(people))
        else:
            print(json.dumps(people))
        return 0
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

AUTHED_COMMANDS = {
    'find', 'show', 'directory', 'me', 'contacts',
    'manager', 'direct-reports', 'org-chart', 'photo', 'groups',
    'contact-create', 'contact-update', 'contact-delete',
}


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


_TOP_FLAG = schema_mod.flag('--top', value='<n>', summary='Alias for --limit')
_SELECT_FLAG = schema_mod.flag('--select', value='<props>', summary='OData $select passthrough')
_FILTER_FLAG = schema_mod.flag('--filter', value='<expr>', summary='OData $filter passthrough')

_FIND_FLAGS = [
    schema_mod.flag('<query>', summary='Search query (positional, free text)', required=True),
    schema_mod.flag('--limit', value='<n>', summary='Max results (default 25, cap 100)'),
    _TOP_FLAG, _SELECT_FLAG, _FILTER_FLAG,
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
]

_DIRECTORY_FLAGS = [
    schema_mod.flag('<query>', summary='Search query (positional, free text)', required=True),
    schema_mod.flag('--limit', value='<n>', summary='Max results per page (default 25, cap 100)'),
    _TOP_FLAG, _SELECT_FLAG, _FILTER_FLAG,
    schema_mod.flag('--all', summary='Follow @odata.nextLink until exhausted'),
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
]

_SHOW_FLAGS = [
    schema_mod.flag('<id-or-email>', summary='Object id or email (positional)', required=True),
    schema_mod.flag('--pretty', summary='Human-readable card (default: JSON)'),
]

_ME_FLAGS = [
    schema_mod.flag('--pretty', summary='Human-readable card (default: JSON)'),
]

_CONTACTS_FLAGS = [
    schema_mod.flag('--search', value='<term>', summary='Search contacts'),
    schema_mod.flag('--limit', value='<n>', summary='Max results per page (default 50, cap 100)'),
    _TOP_FLAG, _SELECT_FLAG, _FILTER_FLAG,
    schema_mod.flag('--all', summary='Follow @odata.nextLink until exhausted'),
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
]

_MANAGER_FLAGS = [
    schema_mod.flag('<id-or-email>', summary='User id or email (positional, default: me)'),
    schema_mod.flag('--pretty', summary='Human-readable card (default: JSON)'),
]

_DIRECT_REPORTS_FLAGS = [
    schema_mod.flag('<id-or-email>', summary='User id or email (positional, default: me)'),
    schema_mod.flag('--all', summary='Follow @odata.nextLink until exhausted'),
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
]

_ORG_CHART_FLAGS = [
    schema_mod.flag('<id-or-email>', summary='User id or email (positional, default: me)'),
    schema_mod.flag('--depth', value='<n>', summary='Manager levels to walk up (default 1, cap 3)'),
    schema_mod.flag('--pretty', summary='Human-readable tree (default: JSON)'),
]

_PHOTO_FLAGS = [
    schema_mod.flag('<id-or-email>', summary='User id or email (positional, default: me)'),
    schema_mod.flag('--out', value='<path>', summary='Write to file instead of stdout'),
]

_GROUPS_FLAGS = [
    schema_mod.flag('<id-or-email>', summary='User id or email (positional, default: me)'),
    schema_mod.flag('--limit', value='<n>', summary='Max results per page (default 50, cap 100)'),
    _TOP_FLAG,
    schema_mod.flag('--all', summary='Follow @odata.nextLink until exhausted'),
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
]

_CONTACT_FIELD_FLAGS = [
    schema_mod.flag('--name', value='<name>', summary='Display name'),
    schema_mod.flag('--given', value='<name>', summary='Given (first) name'),
    schema_mod.flag('--surname', value='<name>', summary='Surname (last name)'),
    schema_mod.flag('--email', value='<addr>', summary='Email address'),
    schema_mod.flag('--mobile', value='<phone>', summary='Mobile phone'),
    schema_mod.flag('--company', value='<name>', summary='Company name'),
    schema_mod.flag('--title', value='<title>', summary='Job title'),
]

_CONTACT_UPDATE_FLAGS = [
    schema_mod.flag('<contact-id>', summary='Contact id (positional)', required=True),
    *_CONTACT_FIELD_FLAGS,
]

_CONTACT_DELETE_FLAGS = [
    schema_mod.flag('--id', value='<contact-id>', summary='Contact id (flag or positional)', required=True),
    schema_mod.flag('--confirm', summary='Skip confirmation prompt'),
]

_CONFIG_FLAGS = [
    schema_mod.flag('--profile', value='<alias>', summary='Pin a default owa-piggy profile alias (owa_piggy_profile)'),
]

COMMAND_SCHEMA = [
    schema_mod.command('find', 'Search recent people', auth='graph', flags=_FIND_FLAGS),
    schema_mod.command('show', 'Show one person', auth='graph', flags=_SHOW_FLAGS),
    schema_mod.command('directory', 'Search company directory', auth='graph', flags=_DIRECTORY_FLAGS),
    schema_mod.command('me', 'Show authenticated user', auth='graph', flags=_ME_FLAGS),
    schema_mod.command('manager', "Show a user's manager", auth='graph', flags=_MANAGER_FLAGS),
    schema_mod.command('direct-reports', "List a user's direct reports", auth='graph', flags=_DIRECT_REPORTS_FLAGS),
    schema_mod.command('org-chart', 'Walk managers up and reports down', auth='graph', flags=_ORG_CHART_FLAGS),
    schema_mod.command('photo', "Fetch a user's photo (binary)", auth='graph', output='binary', flags=_PHOTO_FLAGS),
    schema_mod.command('groups', 'List group memberships', auth='graph', flags=_GROUPS_FLAGS),
    schema_mod.command('contacts', 'List personal contacts', auth='graph', flags=_CONTACTS_FLAGS),
    schema_mod.command(
        'contact-create', 'Create a personal contact', auth='graph',
        mutates=True, idempotent=False, flags=_CONTACT_FIELD_FLAGS,
    ),
    schema_mod.command(
        'contact-update', 'Update a personal contact', auth='graph',
        mutates=True, idempotent=True, flags=_CONTACT_UPDATE_FLAGS,
    ),
    schema_mod.command(
        'contact-delete', 'Delete a personal contact', auth='graph',
        mutates=True, destructive=True, confirmation=True, idempotent=False,
        flags=_CONTACT_DELETE_FLAGS,
    ),
    schema_mod.command('refresh', 'Force a token refresh', auth='graph'),
    schema_mod.command('config', 'View or update configuration', mutates=True, flags=_CONFIG_FLAGS),
]


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-people', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled

    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] in ('--version', '-v'):
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
        cmd, rest, tool='owa-people', commands=COMMAND_SCHEMA,
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

    # Bare-query shorthand: a first token that isn't a known command (and
    # isn't a flag) is treated as the start of a find query, so
    # `owa-people nina` == `owa-people find nina`. A leading-dash token is
    # still a genuine error (unknown flag, not a name).
    if cmd not in AUTHED_COMMANDS:
        if cmd.startswith('-'):
            raise UsageError(f"Unknown command: {cmd}. Run 'owa-people help' for usage.")
        cmd, rest = 'find', argv

    schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)

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
    if cmd == 'manager':
        return cmd_manager(rest, config, access_token, api_base)
    if cmd == 'direct-reports':
        return cmd_direct_reports(rest, config, access_token, api_base)
    if cmd == 'org-chart':
        return cmd_org_chart(rest, config, access_token, api_base)
    if cmd == 'photo':
        return cmd_photo(rest, config, access_token, api_base)
    if cmd == 'groups':
        return cmd_groups(rest, config, access_token, api_base)
    if cmd == 'contact-create':
        return cmd_contact_create(rest, config, access_token, api_base)
    if cmd == 'contact-update':
        return cmd_contact_update(rest, config, access_token, api_base)
    if cmd == 'contact-delete':
        return cmd_contact_delete(rest, config, access_token, api_base)

    return 1


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-people', sys.argv[1:] if argv is None else argv, _main,
    )
