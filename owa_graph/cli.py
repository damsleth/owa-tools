"""Argument parsing and dispatch for the `owa-graph` command.

owa-graph is verb-first: `owa-graph GET /me`, `owa-graph POST /me/sendMail
--body @msg.json`. JSON on stdout, logs on stderr, --pretty for humans,
--curl/--az to render the equivalent shell command without executing.

Subcommands are parsed manually (no argparse subparsers) to keep the
code flat and to mirror owa-cal/owa-mail. Each cmd_* fn is responsible
for its own flag loop.
"""
import json
import os
import sys

from owa_core import jwt as jwt_mod

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from . import ctx as ctx_mod
from . import emit as emit_mod
from . import format as format_mod
from . import paths as paths_mod
from . import resources as resources_mod
from . import scopes as scopes_mod

HTTP_VERBS = {'GET', 'POST', 'PATCH', 'PUT', 'DELETE'}
RESERVED_SUBCOMMANDS = {'refresh', 'config', 'batch', 'help'}


def _error(msg):
    print(f'ERROR: {msg}', file=sys.stderr)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('GRAPH_DEBUG') == '1'


def _require_value(flag, args):
    if not args:
        _error(f'{flag} requires a value')
        sys.exit(1)
    return args[0], args[1:]


def print_help():
    groups_block_lines = [
        f"  {name:<10}  {resources_mod.GROUP_DESCRIPTIONS.get(name, '')}"
        for name in resources_mod.known_groups()
    ]
    groups_block = '\n'.join(groups_block_lines)
    print("""owa-graph - Microsoft Graph CLI for one-off queries

Usage: owa-graph <METHOD> <path> [options]
       owa-graph <group> <shortcut> [options]
       owa-graph batch <file|-> [--pretty] [--retry]
       owa-graph refresh
       owa-graph config [--profile <alias>] [--app-client-id <id>] [--audience <name>]

METHOD: GET | POST | PATCH | PUT | DELETE  (case-insensitive)
path:   /me, /users, '/users?$top=5', me/messages/<id>  (leading slash optional)

Resource groups (run `owa-graph <group>` for shortcuts):
""" + groups_block + """

Per-call options:
  --body <json|@file|->     Request body. Literal JSON, @path-to-file,
                            or - to read from stdin.
  --header K=V              Extra header (repeatable).
  --query K=V               OData query parameter (repeatable; URL-encoded).
  --select F1,F2            Shortcut for --query '$select=F1,F2'.
  --top N                   Shortcut for --query '$top=N'.
  --filter EXPR             Shortcut for --query '$filter=EXPR'.
  --count                   Shortcut for $count=true (sets ConsistencyLevel:
                            eventual; required for advanced directory queries).
  --search EXPR             Shortcut for $search="EXPR" (also sets
                            ConsistencyLevel: eventual).
  --all                     Follow @odata.nextLink until exhausted.
                            Output: single {"value": [...]} unless --ndjson.
  --ndjson                  Stream items one per line (jq-friendly).
                            Pairs with --all; standalone splits a single
                            page's value array.
  --retry                   Honor Retry-After once on 429/503 (capped at 60s).
  --beta                    Use https://graph.microsoft.com/beta (graph audience only).
  --audience <name>         Forward to owa-piggy. Default: graph.
                            Known: graph, outlook, teams, azure, keyvault,
                            storage, sql, outlook365, substrate, manage,
                            powerbi, flow, devops.
  --pretty                  Human-readable output (tables for users/messages/
                            drive items; indented JSON otherwise).
  --raw                     Print raw response bytes (no JSON parsing).
                            Useful for $value endpoints that return binary.
  --curl                    Print equivalent curl command and exit. No HTTP call.
  --az                      Print equivalent `az rest` command and exit.

Global options:
  --debug, --verbose        Print HTTP requests and response bodies on errors
                            (also: GRAPH_DEBUG=1).
  --profile <alias>         Forward to owa-piggy as --profile <alias>
                            (overrides owa_piggy_profile in the config file
                            and OWA_PROFILE in the env).

Environment:
  GRAPH_DEBUG=1             Same as --debug.
  OWA_PROFILE=<alias>       Inherited by the owa-piggy subprocess. Lower
                            precedence than --profile and the config file pin.
  OWA_REFRESH_TOKEN,        Env-only mode: passed through to owa-piggy so it
  OWA_TENANT_ID             can mint tokens with no on-disk config. Enables
                            single-line uvx (`uvx owa-graph GET /me`).
  OWA_GRAPH_NO_SCOPE_HINTS=1
                            Suppress the pre-flight scope-mismatch warning
                            that fires before a request whose scope isn't in
                            the JWT. Useful for CI / scripted use.

Auth:
  owa-graph shells out to owa-piggy for a fresh access token on every
  call. owa-piggy owns the refresh token; owa-graph stores only an
  optional profile alias and a default audience.

  Quickstart:
    brew install damsleth/tap/owa-piggy
    owa-piggy setup                 # or: setup --profile work

Scope caveat:
  The OWA first-party SPA client owa-piggy borrows does NOT carry full
  Graph permissions. Reads on /me, /users, /me/joinedTeams, /groups,
  /planner, /me/drive and directory work; mail/calendar/contacts/todo/
  sites/presence shortcuts return 403 on this path. Use the audience-
  specific siblings (owa-cal, owa-mail) which target the Outlook REST
  audience. See README.md "Scope matrix" for per-shortcut details.

Examples:
  owa-graph GET /me
  owa-graph GET '/users?$top=5' --pretty
  owa-graph GET /users --all --ndjson | jq -c .displayName
  owa-graph GET /users --search 'displayName:Bob' --count
  owa-graph GET /me/messages --top 10 --select id,subject,from
  owa-graph POST /me/sendMail --body @mail.json
  owa-graph PATCH /me/messages/AAMk... --body '{"isRead":true}'
  owa-graph GET /me/drive/root/children --beta
  owa-graph GET /me --curl | pbcopy
  owa-graph GET me/events --audience outlook --pretty
  owa-graph batch requests.json --pretty
  owa-graph refresh""")


def _emit_scope_hint(method, path, audience, access_token):
    """Pre-flight advisory: warn if the request's required scopes aren't
    in the JWT. Always best-effort - silently no-ops on any failure so
    the hint can't break a working call.

    Suppressed when:
      * audience is not 'graph' (manifest only covers Graph paths),
      * OWA_GRAPH_NO_SCOPE_HINTS=1 in the env (CI/scripted use),
      * the manifest has no entry for (path, verb) - common for paths
        we haven't curated yet.
    """
    if audience != 'graph':
        return
    if os.environ.get('OWA_GRAPH_NO_SCOPE_HINTS') == '1':
        return
    required = scopes_mod.required_scopes(method, path)
    if not required:
        return
    have = jwt_mod.scopes_in_token(access_token)
    missing = [s for s in required if s not in have]
    if not missing:
        return
    miss = ', '.join(missing)
    print(
        f'warn: this call requires {miss}; your token does not carry it. '
        f'Likely 403. Set OWA_GRAPH_NO_SCOPE_HINTS=1 to silence this warning.',
        file=sys.stderr,
    )


def _cmd_internal_complete(args):
    """Hidden subcommand used by the shell completion scripts. Stable
    enough for them to depend on; deliberately not advertised in help.

    Usage:
      owa-graph __complete paths [v1.0|beta]   # one path per line
    """
    if not args:
        return 1
    head, rest = args[0], args[1:]
    if head == 'paths':
        endpoint = rest[0] if rest else 'v1.0'
        paths_mod.dump_paths(endpoint)
        return 0
    return 1


def _resolve_body(arg):
    """Returns (body_value, is_file_ref). body_value is the JSON-decoded
    object for literal/stdin input, or the raw string for @file-refs
    (which we keep as a path so curl/az can handle the file)."""
    if arg == '-':
        raw = sys.stdin.read()
        try:
            return json.loads(raw), False
        except json.JSONDecodeError as e:
            _error(f'stdin body is not valid JSON: {e}')
            sys.exit(1)
    if arg.startswith('@'):
        path = arg[1:]
        return path, True
    try:
        return json.loads(arg), False
    except json.JSONDecodeError as e:
        _error(f'--body is not valid JSON: {e}')
        sys.exit(1)


def _read_file_body(path):
    """Read a @file body from disk for actual HTTP execution (not curl/az
    rendering, which keeps the @path reference)."""
    try:
        with open(path, 'rb') as f:
            return f.read()
    except OSError as e:
        _error(f'cannot read body file {path!r}: {e}')
        sys.exit(1)


def cmd_request(method, path, args, config):
    body = None
    body_is_file_ref = False
    headers = {}
    query_pairs = []
    audience = config.get('default_audience') or 'graph'
    beta = False
    pretty = False
    raw = False
    emit_mode = None
    all_pages = False
    ndjson = False
    do_retry = False

    while args:
        flag, args = args[0], args[1:]
        if flag == '--body':
            v, args = _require_value(flag, args)
            body, body_is_file_ref = _resolve_body(v)
        elif flag == '--header':
            v, args = _require_value(flag, args)
            if '=' not in v:
                _error(f"--header expects K=V, got: {v!r}")
                return 1
            k, _, val = v.partition('=')
            headers[k.strip()] = val.strip()
        elif flag == '--query':
            v, args = _require_value(flag, args)
            if '=' not in v:
                _error(f"--query expects K=V, got: {v!r}")
                return 1
            k, _, val = v.partition('=')
            query_pairs.append((k.strip(), val.strip()))
        elif flag == '--select':
            v, args = _require_value(flag, args)
            query_pairs.append(('$select', v))
        elif flag == '--top':
            v, args = _require_value(flag, args)
            query_pairs.append(('$top', v))
        elif flag == '--filter':
            v, args = _require_value(flag, args)
            query_pairs.append(('$filter', v))
        elif flag == '--count':
            # $count=true on directory objects requires
            # ConsistencyLevel: eventual, otherwise Graph 400s with a
            # "Request_UnsupportedQuery" message that's hard to
            # diagnose. Set the header unless the caller already did.
            query_pairs.append(('$count', 'true'))
            headers.setdefault('ConsistencyLevel', 'eventual')
        elif flag == '--search':
            v, args = _require_value(flag, args)
            # Graph wants the search expression wrapped in double
            # quotes (`$search="value"`). Same eventual-consistency
            # requirement as --count.
            query_pairs.append(('$search', f'"{v}"'))
            headers.setdefault('ConsistencyLevel', 'eventual')
        elif flag == '--audience':
            audience, args = _require_value(flag, args)
        elif flag == '--beta':
            beta = True
        elif flag == '--pretty':
            pretty = True
        elif flag == '--raw':
            raw = True
        elif flag == '--all':
            all_pages = True
        elif flag == '--ndjson':
            ndjson = True
        elif flag == '--retry':
            do_retry = True
        elif flag == '--curl':
            emit_mode = 'curl'
        elif flag == '--az':
            emit_mode = 'az'
        else:
            _error(f'Unknown flag: {flag}'); return 1

    if all_pages and raw:
        _error('--all and --raw are incompatible (collection vs single binary)')
        return 1
    if ndjson and raw:
        _error('--ndjson and --raw are incompatible')
        return 1

    debug = _debug_enabled(config)

    # In emit mode we still need a token (so the rendered command is
    # immediately runnable) but we never make the actual API call.
    access_token, api_base = auth_mod.setup_auth(
        config, audience=audience, beta=beta, debug=debug,
    )

    # Pre-flight scope hint. Skip in emit mode - the user is asking for
    # a curl/az command to share or pipe, not actually calling Graph
    # right now, so a warning isn't useful.
    if emit_mode is None:
        _emit_scope_hint(method, path, audience, access_token)

    url = api_mod.build_url(api_base, path, query_pairs)

    if emit_mode == 'curl':
        print(emit_mod.render_curl(
            method, url, access_token,
            headers=headers, body=body, body_is_file_ref=body_is_file_ref,
        ))
        return 0
    if emit_mode == 'az':
        print(emit_mod.render_az(
            method, url, access_token,
            headers=headers, body=body, body_is_file_ref=body_is_file_ref,
        ))
        return 0

    # Resolve @file body for the actual call.
    request_body = body
    if body_is_file_ref:
        request_body = _read_file_body(body)

    if all_pages:
        return _emit_paginated(
            method, url, access_token, headers,
            ndjson=ndjson, pretty=pretty, debug=debug, retry=do_retry,
        )

    # api_request joins base+endpoint with `/`, but we already built the
    # full URL above. Pass a synthetic base of '' and the absolute URL
    # as the endpoint - api_request honors `http`-prefixed endpoints.
    result = api_mod.api_request(
        method, '', url, access_token,
        body=request_body, extra_headers=headers,
        debug=debug, raw=raw, retry=do_retry,
    )

    if result is None:
        return 1

    if raw:
        # bytes - write directly to the underlying stdout buffer to avoid
        # encoding mangling (Graph $value endpoints can return binary).
        sys.stdout.buffer.write(result)
        return 0

    if ndjson:
        _emit_ndjson_single(result)
        return 0

    if pretty:
        print(format_mod.format_pretty(result))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


def _emit_paginated(method, url, access_token, headers,
                    ndjson=False, pretty=False, debug=False, retry=False):
    """Drive api.paginate and emit results in the requested form.

    --ndjson streams each item; --pretty buffers everything and renders
    the table once (we can't pretty-print incrementally without breaking
    column alignment); default emits a single `{"value": [...]}` wrapper
    matching Graph's collection shape so jq pipelines keep working."""
    items_iter = api_mod.paginate(
        method, url, access_token,
        extra_headers=headers, debug=debug, retry=retry,
    )
    if ndjson:
        emitted = 0
        for item in items_iter:
            print(json.dumps(item, ensure_ascii=False))
            emitted += 1
        # Treat zero items as success - empty collection is a valid result.
        return 0
    items = list(items_iter)
    if pretty:
        print(format_mod.format_pretty({'value': items}))
    else:
        print(json.dumps({'value': items}, ensure_ascii=False))
    return 0


def _emit_ndjson_single(result):
    """Emit a single (non-paginated) response as NDJSON. If `value` is a
    list, each item gets its own line; otherwise the whole response is
    one line."""
    if isinstance(result, dict) and isinstance(result.get('value'), list):
        for item in result['value']:
            print(json.dumps(item, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False))


def cmd_batch(args, config):
    """Post a Graph JSON-batch request body and surface the response.

    The body is read from a file path or `-` for stdin. If the body is
    a flat array we wrap it in `{"requests": [...]}` so callers don't
    have to remember Graph's outer envelope; objects are passed through
    verbatim. Default output is the raw JSON response (which is itself
    a `{"responses": [...]}` envelope); --pretty renders the per-request
    status table.
    """
    pretty = False
    do_retry = False
    source = None
    while args:
        a, args = args[0], args[1:]
        if a == '--pretty':
            pretty = True
        elif a == '--retry':
            do_retry = True
        elif a.startswith('--'):
            _error(f'Unknown flag: {a}'); return 1
        elif source is None:
            source = a
        else:
            _error(f'Unexpected argument: {a!r}'); return 1

    if source is None:
        _error('batch requires a file path or - for stdin')
        return 1

    if source == '-':
        raw_body = sys.stdin.read()
    else:
        path = source[1:] if source.startswith('@') else source
        try:
            with open(path) as f:
                raw_body = f.read()
        except OSError as e:
            _error(f'cannot read {path!r}: {e}')
            return 1

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as e:
        _error(f'batch body is not valid JSON: {e}')
        return 1

    if isinstance(body, list):
        body = {'requests': body}
    elif not isinstance(body, dict) or 'requests' not in body:
        _error("batch body must be a list of requests or "
               "a {'requests': [...]} object")
        return 1

    debug = _debug_enabled(config)
    audience = config.get('default_audience') or 'graph'
    access_token, api_base = auth_mod.setup_auth(
        config, audience=audience, debug=debug,
    )
    result = api_mod.api_request(
        'POST', api_base, '$batch', access_token,
        body=body, debug=debug, retry=do_retry,
    )
    if result is None:
        return 1
    if pretty:
        print(format_mod.format_pretty(result))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_refresh(args, config):
    if args:
        _error(f'Unknown flag: {args[0]}'); return 1
    _info('Refreshing token...')
    debug = _debug_enabled(config)
    audience = config.get('default_audience') or 'graph'
    access = auth_mod.do_token_refresh(config, audience=audience, debug=debug)
    if not access:
        _error('Token refresh failed.')
        return 1
    # /me only exists on Graph and Outlook REST. For other audiences
    # (Azure Mgmt, Key Vault, etc.) we just confirm we got a token.
    if audience in ('graph', 'outlook', 'outlook365'):
        api_base = auth_mod.resolve_api_base(audience)
        me = api_mod.api_get(api_base, 'me', access, debug=debug)
        if not isinstance(me, dict):
            _error('Auth verification failed.')
            return 1
        name = me.get('displayName') or me.get('DisplayName')
        if name:
            _info(f'Authenticated as {name}')
    else:
        _info(f'Token minted for audience {audience!r}.')
    return 0


def cmd_config(args, config):
    """Handled specially: no auth required."""
    profile = audience = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--profile':
            profile, args = _require_value(flag, args)
        elif flag == '--audience':
            audience, args = _require_value(flag, args)
        else:
            _error(f'Unknown flag: {flag}'); return 1

    wrote = False
    if profile:
        config_mod.config_set('owa_piggy_profile', profile)
        _info(f'owa-piggy profile saved: {profile}'); wrote = True
    if audience:
        config_mod.config_set('default_audience', audience)
        _info(f'Default audience saved: {audience}'); wrote = True

    if not wrote:
        _info(f'Config file: {config_mod.CONFIG_PATH}')
        if config.get('owa_piggy_profile'):
            _info(f"  owa_piggy_profile={config.get('owa_piggy_profile')}")
        else:
            _info('  owa_piggy_profile=(not set - owa-piggy picks its default)')
        _info(f"  default_audience={config.get('default_audience')}")
    return 0


def _print_group_help(group_name, group_module):
    """Pretty-print the shortcut table for `owa-graph <group>` (no args
    or `help`/`--help`). Plan v0.3 keeps per-shortcut --help out of v0.3."""
    desc = resources_mod.GROUP_DESCRIPTIONS.get(group_name, '')
    print(f'owa-graph {group_name} - {desc}' if desc else f'owa-graph {group_name}')
    print()
    print('Shortcuts:')
    width = max(len(k) for k in group_module.COMMANDS) if group_module.COMMANDS else 0
    for name, entry in group_module.COMMANDS.items():
        help_text = entry[1]
        print(f'  {name:<{width}}  {help_text}')
    print()
    print('Common flags accepted by every shortcut:')
    print('  --pretty   Human-readable output (table for known shapes, indented JSON otherwise)')
    print('  --ndjson   Stream collection items one JSON object per line')
    print('  --retry    Honor Retry-After once on 429/503')


def _dispatch_resource_group(group_name, args, config):
    """Route `owa-graph <group> <shortcut> [args]` to a resource handler.

    Strips the cross-cutting emit flags (--pretty/--ndjson/--retry) before
    handing argv to the per-shortcut handler so handler-side _argv.parse
    only sees its own flags. Each handler is 5-15 LOC; the dispatcher
    owns the auth + RequestContext setup so the per-handler code stays
    flat.
    """
    try:
        group_module = resources_mod.load_group(group_name)
    except KeyError:
        _error(f'unknown resource group: {group_name!r}')
        return 1

    if not args or args[0] in ('help', '--help', '-h'):
        _print_group_help(group_name, group_module)
        return 0

    shortcut, rest = args[0], args[1:]
    if shortcut not in group_module.COMMANDS:
        _error(
            f"unknown {group_name} shortcut: {shortcut!r}. "
            f"Try `owa-graph {group_name}` for the list."
        )
        return 1

    pretty = ndjson = retry = False
    handler_args = []
    for a in rest:
        if a == '--pretty':
            pretty = True
        elif a == '--ndjson':
            ndjson = True
        elif a == '--retry':
            retry = True
        else:
            handler_args.append(a)

    debug = _debug_enabled(config)
    audience = config.get('default_audience') or 'graph'
    access_token, api_base = auth_mod.setup_auth(
        config, audience=audience, debug=debug,
    )
    ctx = ctx_mod.RequestContext(
        config=config, access_token=access_token, api_base=api_base,
        debug=debug, pretty=pretty, ndjson=ndjson, retry=retry,
    )
    handler = group_module.COMMANDS[shortcut][0]
    try:
        return handler(handler_args, ctx)
    except ValueError as e:
        _error(str(e))
        return 1


def _first_nonglobal(argv):
    """Return the first argv token that isn't a global flag or its
    value. Used to decide whether `--profile` later in argv is the
    global form (forwarded to owa-piggy) or the subcommand form (writes
    to the config file under `owa-graph config`)."""
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


def main():
    argv = sys.argv[1:]

    if not argv or argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] == '--version':
        print(f'owa-graph {__version__}')
        return 0

    is_config_cmd = _first_nonglobal(argv) == 'config'

    debug_flag = False
    profile_override = ''
    filtered = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--debug', '--verbose'):
            debug_flag = True
            i += 1
            continue
        if a == '--profile' and not (is_config_cmd and 'config' in filtered):
            if i + 1 >= len(argv):
                _error('--profile requires a value'); return 1
            profile_override = argv[i + 1]
            i += 2
            continue
        filtered.append(a)
        i += 1
    argv = filtered

    if not argv:
        print_help()
        return 0

    config = config_mod.load_config()
    if debug_flag:
        config['debug'] = True
        _info('DEBUG: verbose logging enabled')
    if profile_override:
        config['owa_piggy_profile'] = profile_override

    head = argv[0]
    rest = argv[1:]

    if head == 'config':
        return cmd_config(rest, config)
    if head == 'refresh':
        return cmd_refresh(rest, config)
    if head == 'batch':
        return cmd_batch(rest, config)
    if head in ('help', '--help', '-h'):
        print_help()
        return 0
    if head == '__complete':
        return _cmd_internal_complete(rest)

    if head in resources_mod.known_groups():
        return _dispatch_resource_group(head, rest, config)

    method = head.upper()
    if method not in HTTP_VERBS:
        _error(
            f"Unknown command: {head!r}. "
            f"Expected an HTTP verb ({', '.join(sorted(HTTP_VERBS))}) "
            f"or one of: {', '.join(sorted(RESERVED_SUBCOMMANDS))}. "
            f"Run 'owa-graph help' for usage."
        )
        return 1

    if not rest:
        _error(f'{method} requires a path (e.g. `owa-graph {method} /me`)')
        return 1
    path, request_args = rest[0], rest[1:]
    return cmd_request(method, path, request_args, config)
