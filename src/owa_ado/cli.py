"""Argument parsing and dispatch for `owa-ado`.

A thin CLI over the Azure DevOps REST API, authenticated through the
owa-piggy broker (`--audience devops`). Commands cover the four surfaces
people reach for daily: work items, boards/sprints, repos & pull
requests, and pipelines.

Org/project resolution (most-specific wins):
  org:     --org/-o  >  OWA_ADO_ORG  >  config ado_org
  project: --project/-P  >  OWA_ADO_PROJECT  >  config ado_project

`projects` needs only an org; everything else is project-scoped. JSON is
the default output; `--pretty` renders a table for humans.
"""
import json
import os
import sys
from urllib.parse import quote

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core.errors import UsageError, _require_value

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from . import format as fmt
from . import resources as res


def _error(msg):
    from owa_core.errors import emit_message
    return emit_message(msg)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('ADO_DEBUG') == '1'


def _resolve_org(config):
    org = (os.environ.get('OWA_ADO_ORG', '').strip()
           or config.get('ado_org', '').strip())
    if not org:
        raise UsageError(
            'no Azure DevOps organisation set. Pass --org <org>, export '
            'OWA_ADO_ORG, or run: owa-ado config --org <org>'
        )
    return org


def _resolve_project(config):
    project = (os.environ.get('OWA_ADO_PROJECT', '').strip()
               or config.get('ado_project', '').strip())
    if not project:
        raise UsageError(
            'no Azure DevOps project set. Pass --project <name>, export '
            'OWA_ADO_PROJECT, or run: owa-ado config --project <name>'
        )
    return project


def print_help():
    print("""owa-ado - Azure DevOps CLI for Outlook / Microsoft 365 identities

Usage: owa-ado <command> [options]

Global options:
  --debug, --verbose   Print HTTP requests and error bodies (also ADO_DEBUG=1)
  --profile <alias>    Forward to owa-piggy as --profile <alias>
  --org, -o <org>      Azure DevOps organisation (overrides config/env)
  --project, -P <name> Project (overrides config/env; not needed by `projects`)

Commands:
  projects             List projects in the organisation.
  sprints              List iterations for a team.        (alias: iterations)
                       --team <name>   (default: "<project> Team")
                       --current       Only the current iteration.
  wi [<id>]            Without an id: list work items (WIQL). With an id:
                       show one.                          (alias: workitems)
                       --detailed      (show) add description + attachments.
                       --full          (show) raw full REST payload.
                       --mine          Assigned to me (default when no --query).
                       --state <s>     Filter by state.
                       --type <t>      Filter by work-item type.
                       --top <n>       Cap results (default 50).
                       --query <wiql>  Raw WIQL (overrides the builder).
  wi-create            Create a work item.
                       --type <t> --title <t> [--field path=value]...
                       [--assign @me|<email>] [--parent <id>]
  wi-update <id>       Update a work item.
                       [--state <s>] [--title <t>] [--field path=value]...
  wi-comment <id>      Add a comment to a work item.   --text <body>
  wi-link <id>         Add a link/relation to a work item.
                       --target <id> [--rel parent|child|related|successor|...]
  wi-unlink <id>       Remove a link to a target work item.
                       --target <id> [--rel <name>]
  wi-delete <id>       Delete a work item (confirm-gated). [--destroy]
  repos                List repositories.                 (alias: repositories)
  prs [<id>]          List pull requests, or show one by id.
                       --repo <name>   Scope to one repository.
                       --status active|completed|abandoned|all  (default active)
                       --top <n>       Cap results (default 50).
                       --all           Page through all results (capped by --top).
  pipelines            List pipeline definitions.
  runs                 List recent pipeline runs (builds).
                       --pipeline <id> Filter to one definition.
                       --top <n>       Cap results (default 20).
                       --all           Page through all runs (capped by --top).
  refresh              Force a token refresh and verify auth.
  config               View or update configuration.
                       [--unset <key>]... [--clear]
  help                 Show this help.

Common options:
  --pretty             Human-readable table/view (default: JSON).
  --all                Follow continuation tokens until exhausted
                       (projects, repos, pipelines, prs, runs).
  --api-version <ver>  Override the DevOps api-version for one call.
  --confirm            Skip confirmation prompts (wi-* mutations).

Examples:
  owa-ado config --org Norconsult-Group --project NOCOS
  owa-ado projects --pretty
  owa-ado wi --mine --pretty
  owa-ado wi 12345 --pretty
  owa-ado wi-create --type Task --title "Wire reseed" --assign @me --confirm
  owa-ado prs --status active --pretty
  owa-ado pipelines --pretty
  owa-ado runs --top 10 --pretty
""")
    print()
    print(schema_mod.MULTI_PROFILE_HELP)
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _emit(items, pretty, formatter):
    if pretty:
        print(formatter(items))
    else:
        print(json.dumps(items))
    return 0


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_projects(args, config, token, base):
    pretty, all_pages = _parse_list_flags(args, allow_all=True)
    debug = _debug_enabled(config)
    if all_pages:
        items = api_mod.ado_paginate(base, '_apis/projects', token, debug=debug)
    else:
        payload = api_mod.ado_request('GET', base, '_apis/projects', token, debug=debug)
        items = payload.get('value') if isinstance(payload, dict) else None
    if items is None:
        return 1
    return _emit([res.normalize_project(p) for p in items], pretty, fmt.format_projects)


def cmd_sprints(args, config, token, base):
    pretty = False
    current = False
    team = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--current':
            current = True
        elif flag == '--team':
            team, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')
    project = _resolve_project(config)
    team = team or f'{project} Team'
    endpoint = f'{project}/{team}/_apis/work/teamsettings/iterations'
    query = {'$timeframe': 'current'} if current else None
    payload = api_mod.ado_request('GET', base, endpoint, token,
                                  query=query, debug=_debug_enabled(config))
    items = payload.get('value') if isinstance(payload, dict) else None
    if items is None:
        return 1
    return _emit([res.normalize_iteration(i) for i in items], pretty, fmt.format_iterations)


def cmd_wi(args, config, token, base):
    pretty = False
    mine = False
    full = detailed = False
    state = wi_type = query = iteration = ''
    top = 50
    wi_id = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--full':
            full = True
        elif flag == '--detailed':
            detailed = True
        elif flag == '--mine':
            mine = True
        elif flag == '--state':
            state, args = _require_value(flag, args)
        elif flag == '--type':
            wi_type, args = _require_value(flag, args)
        elif flag == '--iteration':
            iteration, args = _require_value(flag, args)
        elif flag == '--query':
            query, args = _require_value(flag, args)
        elif flag == '--top':
            raw, args = _require_value(flag, args)
            top = _parse_int(raw, '--top')
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not wi_id:
            wi_id = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')

    debug = _debug_enabled(config)

    # Show a single work item by id. --full dumps the raw REST payload;
    # --detailed adds description + attachments. Both need $expand (which
    # can't be combined with a `fields` filter), so they fetch everything.
    if wi_id:
        if full or detailed:
            query_params = {'$expand': 'all' if full else 'relations'}
        else:
            query_params = {'fields': ','.join(res.WI_FIELDS)}
        payload = api_mod.ado_request(
            'GET', base, f'_apis/wit/workitems/{wi_id}', token,
            query=query_params, debug=debug,
        )
        # Raw payload only as JSON; --pretty falls through to the human view.
        if full and not pretty:
            print(json.dumps(payload))
            return 0
        item = (res.normalize_work_item_detailed(payload) if (detailed or full)
                else res.normalize_work_item(payload))
        if pretty:
            print(fmt.format_work_item(item))
        else:
            print(json.dumps(item))
        return 0

    # List via WIQL. Default to "assigned to me" when no raw query given.
    project = _resolve_project(config)
    if not query:
        if not (mine or state or wi_type or iteration):
            mine = True
        query = res.build_wiql(project=project, mine=mine, state=state,
                               wi_type=wi_type, iteration=iteration)
    # WIQL has no TOP clause; cap the id set server-side with $top instead.
    wiql = api_mod.ado_request(
        'POST', base, f'{project}/_apis/wit/wiql', token,
        body={'query': query}, query={'$top': top}, debug=debug,
    )
    ids = [str(w['id']) for w in (wiql.get('workItems') or []) if w.get('id')]
    ids = ids[:top]
    if not ids:
        return _emit([], pretty, fmt.format_work_items)
    # Batch-get the fields for the matched ids in one call.
    payload = api_mod.ado_request(
        'GET', base, '_apis/wit/workitems', token,
        query={'ids': ','.join(ids), 'fields': ','.join(res.WI_FIELDS)},
        debug=debug,
    )
    items = payload.get('value') if isinstance(payload, dict) else None
    if items is None:
        return 1
    return _emit([res.normalize_work_item(w) for w in items], pretty, fmt.format_work_items)


def _parse_fields(field_args):
    """Turn ['System.Description=foo', 'Priority=2'] into JSON Patch ops.

    Bare field names without a System./Microsoft. prefix are assumed to be
    System.* (the common case); fully-qualified paths are used verbatim.
    """
    ops = []
    for raw in field_args:
        if '=' not in raw:
            raise UsageError(f'--field expects path=value, got: {raw!r}')
        path, _, value = raw.partition('=')
        path = path.strip()
        if '.' not in path:
            path = f'System.{path}'
        ops.append({'op': 'add', 'path': f'/fields/{path}', 'value': value})
    return ops


def cmd_wi_create(args, config, token, base):
    wi_type = title = assign = parent = ''
    confirm = False
    fields = []
    while args:
        flag, args = args[0], args[1:]
        if flag == '--type':
            wi_type, args = _require_value(flag, args)
        elif flag == '--title':
            title, args = _require_value(flag, args)
        elif flag == '--assign':
            assign, args = _require_value(flag, args)
        elif flag == '--parent':
            parent, args = _require_value(flag, args)
        elif flag == '--field':
            val, args = _require_value(flag, args)
            fields.append(val)
        elif flag == '--confirm':
            confirm = True
        else:
            raise UsageError(f'Unknown flag: {flag}')

    if not wi_type or not title:
        raise UsageError('wi-create requires --type and --title')
    project = _resolve_project(config)

    ops = [{'op': 'add', 'path': '/fields/System.Title', 'value': title}]
    if assign:
        ops.append({'op': 'add', 'path': '/fields/System.AssignedTo',
                    'value': '@Me' if assign == '@me' else assign})
    ops.extend(_parse_fields(fields))
    if parent:
        org = _resolve_org(config)
        ops.append({
            'op': 'add', 'path': '/relations/-',
            'value': {
                'rel': 'System.LinkTypes.Hierarchy-Reverse',
                'url': f'{auth_mod.org_base(org)}/_apis/wit/workItems/{parent}',
            },
        })

    if not confirm:
        from owa_core import tty as tty_mod
        try:
            tty_mod.require_confirm_or_tty(action='wi-create')
        except UsageError as error:
            from owa_core.errors import emit_error
            return emit_error(error)
        _info(f'about to create {wi_type}: {title}')
        if not tty_mod.confirm('type "yes" to proceed: ', accepted=('yes',)):
            _info('aborted')
            return 1

    # The type is part of the path: POST .../wit/workitems/$Task
    endpoint = f'{project}/_apis/wit/workitems/${wi_type}'
    payload = api_mod.json_patch('POST', base, endpoint, token,
                                 operations=ops, debug=_debug_enabled(config))
    print(json.dumps(res.normalize_work_item(payload)))
    return 0


def cmd_wi_update(args, config, token, base):
    wi_id = state = title = ''
    confirm = False
    fields = []
    while args:
        flag, args = args[0], args[1:]
        if flag == '--state':
            state, args = _require_value(flag, args)
        elif flag == '--title':
            title, args = _require_value(flag, args)
        elif flag == '--field':
            val, args = _require_value(flag, args)
            fields.append(val)
        elif flag == '--confirm':
            confirm = True
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not wi_id:
            wi_id = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')

    if not wi_id:
        raise UsageError('wi-update requires a work-item id')
    ops = []
    if title:
        ops.append({'op': 'add', 'path': '/fields/System.Title', 'value': title})
    if state:
        ops.append({'op': 'add', 'path': '/fields/System.State', 'value': state})
    ops.extend(_parse_fields(fields))
    if not ops:
        raise UsageError('wi-update needs at least one of --state, --title, --field')

    if not confirm:
        from owa_core import tty as tty_mod
        try:
            tty_mod.require_confirm_or_tty(action='wi-update')
        except UsageError as error:
            from owa_core.errors import emit_error
            return emit_error(error)
        _info(f'about to update work item #{wi_id}')
        if not tty_mod.confirm('type "yes" to proceed: ', accepted=('yes',)):
            _info('aborted')
            return 1

    payload = api_mod.json_patch(
        'PATCH', base, f'_apis/wit/workitems/{wi_id}', token,
        operations=ops, debug=_debug_enabled(config),
    )
    print(json.dumps(res.normalize_work_item(payload)))
    return 0


def _confirm_or_abort(action, message):
    """Shared confirm gate for mutating commands. Returns 0 to proceed, or a
    non-zero exit code (1 abort, 2 not-a-tty) the caller should return."""
    from owa_core import tty as tty_mod
    try:
        tty_mod.require_confirm_or_tty(action=action)
    except UsageError as error:
        from owa_core.errors import emit_error
        return emit_error(error)
    _info(message)
    if not tty_mod.confirm('type "yes" to proceed: ', accepted=('yes',)):
        _info('aborted')
        return 1
    return 0


def cmd_wi_comment(args, config, token, base):
    wi_id = text = api_version = ''
    confirm = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--text':
            text, args = _require_value(flag, args)
        elif flag == '--api-version':
            api_version, args = _require_value(flag, args)
        elif flag == '--confirm':
            confirm = True
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not wi_id:
            wi_id = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')

    if not wi_id:
        raise UsageError('wi-comment requires a work-item id')
    if not text:
        raise UsageError('wi-comment requires --text')
    project = _resolve_project(config)

    if not confirm:
        rc = _confirm_or_abort('wi-comment', f'about to comment on work item #{wi_id}')
        if rc:
            return rc

    # The Comments API is versioned independently and only ships on the
    # preview track; pin a preview version unless the caller overrode it.
    ver = api_version or '7.1-preview.4'
    payload = api_mod.ado_request(
        'POST', base, f'{project}/_apis/wit/workItems/{wi_id}/comments', token,
        body={'text': text}, api_version=ver, debug=_debug_enabled(config),
    )
    print(json.dumps(res.normalize_comment(payload)))
    return 0


def cmd_wi_link(args, config, token, base):
    wi_id = target = rel = api_version = ''
    confirm = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--target':
            target, args = _require_value(flag, args)
        elif flag == '--rel':
            rel, args = _require_value(flag, args)
        elif flag == '--api-version':
            api_version, args = _require_value(flag, args)
        elif flag == '--confirm':
            confirm = True
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not wi_id:
            wi_id = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')

    if not wi_id:
        raise UsageError('wi-link requires a work-item id')
    if not target:
        raise UsageError('wi-link requires --target <id>')
    rel_name = res.resolve_rel(rel or 'related')
    org = _resolve_org(config)
    ver = _api_version(api_version)

    if not confirm:
        rc = _confirm_or_abort('wi-link',
                               f'about to link work item #{wi_id} -> #{target} ({rel_name})')
        if rc:
            return rc

    ops = [{
        'op': 'add', 'path': '/relations/-',
        'value': {
            'rel': rel_name,
            'url': f'{auth_mod.org_base(org)}/_apis/wit/workItems/{target}',
        },
    }]
    payload = api_mod.json_patch(
        'PATCH', base, f'_apis/wit/workitems/{wi_id}', token,
        operations=ops, api_version=ver, debug=_debug_enabled(config),
    )
    print(json.dumps(res.normalize_work_item(payload)))
    return 0


def cmd_wi_unlink(args, config, token, base):
    wi_id = target = rel = api_version = ''
    confirm = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--target':
            target, args = _require_value(flag, args)
        elif flag == '--rel':
            rel, args = _require_value(flag, args)
        elif flag == '--api-version':
            api_version, args = _require_value(flag, args)
        elif flag == '--confirm':
            confirm = True
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not wi_id:
            wi_id = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')

    if not wi_id:
        raise UsageError('wi-unlink requires a work-item id')
    if not target:
        raise UsageError('wi-unlink requires --target <id>')
    ver = _api_version(api_version)
    debug = _debug_enabled(config)

    # JSON Patch removes a relation by index, so fetch the relations first and
    # find the one pointing at the target (optionally narrowed by --rel).
    wanted_rel = res.resolve_rel(rel) if rel else ''
    current = api_mod.ado_request(
        'GET', base, f'_apis/wit/workitems/{wi_id}', token,
        query={'$expand': 'relations'}, api_version=ver, debug=debug,
    )
    relations = (current.get('relations') if isinstance(current, dict) else None) or []
    index = None
    for i, r in enumerate(relations):
        url = r.get('url') or ''
        if url.rstrip('/').rsplit('/', 1)[-1] == str(target):
            if wanted_rel and r.get('rel') != wanted_rel:
                continue
            index = i
            break
    if index is None:
        from owa_core.errors import NotFoundError
        raise NotFoundError(f'no link to #{target} on work item #{wi_id}')

    if not confirm:
        rc = _confirm_or_abort('wi-unlink',
                               f'about to remove link work item #{wi_id} -> #{target}')
        if rc:
            return rc

    ops = [{'op': 'remove', 'path': f'/relations/{index}'}]
    payload = api_mod.json_patch(
        'PATCH', base, f'_apis/wit/workitems/{wi_id}', token,
        operations=ops, api_version=ver, debug=debug,
    )
    print(json.dumps(res.normalize_work_item(payload)))
    return 0


def cmd_wi_delete(args, config, token, base):
    wi_id = api_version = ''
    confirm = destroy = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--api-version':
            api_version, args = _require_value(flag, args)
        elif flag == '--destroy':
            destroy = True
        elif flag == '--confirm':
            confirm = True
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not wi_id:
            wi_id = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')

    if not wi_id:
        raise UsageError('wi-delete requires a work-item id')
    project = _resolve_project(config)
    ver = _api_version(api_version)

    if not confirm:
        where = 'PERMANENTLY (no recycle bin)' if destroy else 'to the recycle bin'
        rc = _confirm_or_abort('wi-delete', f'about to delete work item #{wi_id} {where}')
        if rc:
            return rc

    # destroy=True bypasses the recycle bin (irreversible); default soft-deletes.
    payload = api_mod.ado_request(
        'DELETE', base, f'{project}/_apis/wit/workitems/{wi_id}', token,
        query={'destroy': 'true'} if destroy else None,
        api_version=ver, debug=_debug_enabled(config),
    )
    out = {'id': wi_id, 'deleted': True, 'destroyed': destroy}
    if isinstance(payload, dict) and payload.get('code'):
        out['code'] = payload.get('code')
    print(json.dumps(out))
    return 0


def cmd_repos(args, config, token, base):
    pretty, all_pages = _parse_list_flags(args, allow_all=True)
    project = _resolve_project(config)
    debug = _debug_enabled(config)
    endpoint = f'{project}/_apis/git/repositories'
    if all_pages:
        items = api_mod.ado_paginate(base, endpoint, token, debug=debug)
    else:
        payload = api_mod.ado_request('GET', base, endpoint, token, debug=debug)
        items = payload.get('value') if isinstance(payload, dict) else None
    if items is None:
        return 1
    return _emit([res.normalize_repo(r) for r in items], pretty, fmt.format_repos)


def cmd_prs(args, config, token, base):
    pretty = all_pages = False
    repo = status = api_version = ''
    top = 50
    pr_id = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--all':
            all_pages = True
        elif flag == '--repo':
            repo, args = _require_value(flag, args)
        elif flag == '--api-version':
            api_version, args = _require_value(flag, args)
        elif flag == '--status':
            status, args = _require_value(flag, args)
            _PR_STATUSES = ('active', 'completed', 'abandoned', 'all')
            if status not in _PR_STATUSES:
                raise UsageError(
                    f'--status must be one of: {", ".join(_PR_STATUSES)}'
                )
        elif flag == '--top':
            raw, args = _require_value(flag, args)
            top = _parse_int(raw, '--top')
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not pr_id:
            pr_id = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')

    project = _resolve_project(config)
    debug = _debug_enabled(config)
    ver = _api_version(api_version)

    if pr_id:
        payload = api_mod.ado_request(
            'GET', base, f'{project}/_apis/git/pullrequests/{pr_id}', token,
            api_version=ver, debug=debug,
        )
        pr = res.normalize_pr(payload)
        if pretty:
            print(fmt.format_pr(pr))
        else:
            print(json.dumps(pr))
        return 0

    if repo:
        # Pre-encode the repo segment so a name with reserved chars (notably
        # '/') can't break out of its path segment; build_url keeps '%' safe.
        endpoint = f'{project}/_apis/git/repositories/{quote(repo, safe="")}/pullrequests'
    else:
        endpoint = f'{project}/_apis/git/pullrequests'
    query = {}
    if status:
        query['searchCriteria.status'] = status
    items = _list_items(endpoint, token, base, query, top, all_pages,
                        api_version=ver, debug=debug)
    if items is None:
        return 1
    return _emit([res.normalize_pr(p) for p in items], pretty, fmt.format_prs)


def cmd_pipelines(args, config, token, base):
    pretty, all_pages = _parse_list_flags(args, allow_all=True)
    project = _resolve_project(config)
    debug = _debug_enabled(config)
    endpoint = f'{project}/_apis/pipelines'
    if all_pages:
        items = api_mod.ado_paginate(base, endpoint, token, debug=debug)
    else:
        payload = api_mod.ado_request('GET', base, endpoint, token, debug=debug)
        items = payload.get('value') if isinstance(payload, dict) else None
    if items is None:
        return 1
    return _emit([res.normalize_pipeline(p) for p in items], pretty, fmt.format_pipelines)


def cmd_runs(args, config, token, base):
    pretty = all_pages = False
    pipeline = api_version = ''
    top = 20
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--all':
            all_pages = True
        elif flag == '--pipeline':
            pipeline, args = _require_value(flag, args)
        elif flag == '--api-version':
            api_version, args = _require_value(flag, args)
        elif flag == '--top':
            raw, args = _require_value(flag, args)
            top = _parse_int(raw, '--top')
        else:
            raise UsageError(f'Unknown flag: {flag}')
    project = _resolve_project(config)
    ver = _api_version(api_version)
    query = {}
    if pipeline:
        query['definitions'] = pipeline
    items = _list_items(f'{project}/_apis/build/builds', token, base, query, top,
                        all_pages, api_version=ver, debug=_debug_enabled(config))
    if items is None:
        return 1
    return _emit([res.normalize_build(b) for b in items], pretty, fmt.format_builds)


def cmd_config(args, config):
    profile = org = project = ''
    unset_keys = []
    clear = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--profile':
            profile, args = _require_value(flag, args)
        elif flag in ('--org', '-o'):
            org, args = _require_value(flag, args)
        elif flag in ('--project', '-P'):
            project, args = _require_value(flag, args)
        elif flag == '--unset':
            key, args = _require_value(flag, args)
            if key not in config_mod.ALLOWED_KEYS:
                raise UsageError(
                    f'--unset: unknown key {key!r}; one of: '
                    f'{", ".join(config_mod.ALLOWED_KEYS)}'
                )
            unset_keys.append(key)
        elif flag == '--clear':
            clear = True
        else:
            raise UsageError(f'Unknown flag: {flag}')

    if clear:
        removed = config_mod.config_clear()
        _info(f'config cleared ({removed} key(s) removed)')
        return 0
    if unset_keys:
        for key in unset_keys:
            if config_mod.config_unset(key):
                _info(f'unset {key}')
            else:
                _info(f'{key} was not set')
        return 0

    touched = False
    if profile:
        config_mod.config_set('owa_piggy_profile', profile)
        _info(f'default profile saved: {profile}')
        touched = True
    if org:
        config_mod.config_set('ado_org', org)
        _info(f'default org saved: {org}')
        touched = True
    if project:
        config_mod.config_set('ado_project', project)
        _info(f'default project saved: {project}')
        touched = True
    if touched:
        return 0

    _info(f'Config file: {config_mod.CONFIG_PATH}')
    for key in ('owa_piggy_profile', 'ado_org', 'ado_project'):
        val = config.get(key)
        _info(f'  {key}={val}' if val else f'  {key}=(not set)')
    return 0


def cmd_refresh(args, config):
    if args:
        raise UsageError(f'Unknown flag: {args[0]}')
    _info('Refreshing token...')
    access = auth_mod.do_token_refresh(config, debug=_debug_enabled(config))
    if not access:
        _error('Token refresh failed.')
        return 1
    org = _resolve_org(config)
    base = auth_mod.org_base(org)
    payload = api_mod.ado_request('GET', base, '_apis/projects', access,
                                  query={'$top': 1}, debug=_debug_enabled(config))
    if not isinstance(payload, dict):
        _error('Auth verification failed.')
        return 1
    _info(f'Authenticated against {org} ({payload.get("count", 0)} project(s) visible)')
    return 0


# ---------------------------------------------------------------------------
# Small parse helpers
# ---------------------------------------------------------------------------

def _parse_int(raw, flag):
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise UsageError(f'{flag} expects an integer, got: {raw!r}')


def _api_version(raw):
    """A non-empty --api-version overrides the per-call default; '' keeps it."""
    return raw or api_mod.DEFAULT_API_VERSION


def _list_items(endpoint, token, base, query, top, all_pages, *,
                api_version, debug):
    """Fetch a `value` list, optionally following continuation tokens.

    Without --all: a single page capped at `top`. With --all: page until the
    continuation header is exhausted or `top` is reached; if more pages remain
    when the cap is hit, warn on stderr so the truncation is visible. Returns
    the item list, or None if the single-page payload wasn't a list envelope.
    """
    if all_pages:
        items = api_mod.ado_paginate(base, endpoint, token, query=dict(query),
                                     api_version=api_version, max_items=top, debug=debug)
        if len(items) >= top:
            _info(f'note: results capped at {top}; pass --top to raise the limit')
        return items
    payload = api_mod.ado_request('GET', base, endpoint, token,
                                  query={**query, '$top': top},
                                  api_version=api_version, debug=debug)
    return payload.get('value') if isinstance(payload, dict) else None


def _parse_list_flags(args, *, allow_all=False):
    """Shared --pretty/--all parser for the plain list commands."""
    pretty = all_pages = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--all' and allow_all:
            all_pages = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    return (pretty, all_pages) if allow_all else pretty


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

AUTHED_COMMANDS = {
    'projects', 'sprints', 'wi', 'wi-create', 'wi-update',
    'wi-comment', 'wi-link', 'wi-unlink', 'wi-delete',
    'repos', 'prs', 'pipelines', 'runs',
}


def _command_name(argv):
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--debug', '--verbose'):
            i += 1
            continue
        if a in ('--profile', '--org', '-o', '--project', '-P'):
            i += 2
            continue
        return a
    return ''


_PRETTY = schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)')
_ALL = schema_mod.flag('--all', summary='Follow continuation tokens until exhausted')
_API_VERSION = schema_mod.flag('--api-version', value='<ver>',
                               summary='Override the DevOps api-version for this call')

COMMAND_SCHEMA = [
    schema_mod.command('projects', 'List projects in the organisation',
                       auth='devops', flags=[_ALL, _PRETTY]),
    schema_mod.command('sprints', 'List team iterations', auth='devops', aliases=['iterations'],
                       flags=[
                           schema_mod.flag('--team', value='<name>', summary='Team (default "<project> Team")'),
                           schema_mod.flag('--current', summary='Only the current iteration'),
                           _PRETTY,
                       ]),
    schema_mod.command('wi', 'List work items (WIQL) or show one by id',
                       auth='devops', aliases=['workitems'],
                       flags=[
                           schema_mod.flag('<id>', summary='Work-item id to show (positional)'),
                           schema_mod.flag('--detailed', summary='(show) add description + attachments'),
                           schema_mod.flag('--full', summary='(show) raw full REST payload'),
                           schema_mod.flag('--mine', summary='Assigned to me'),
                           schema_mod.flag('--state', value='<state>', summary='Filter by state'),
                           schema_mod.flag('--type', value='<type>', summary='Filter by work-item type'),
                           schema_mod.flag('--top', value='<n>', summary='Cap results (default 50)'),
                           schema_mod.flag('--query', value='<wiql>', summary='Raw WIQL (overrides builder)'),
                           _PRETTY,
                       ]),
    schema_mod.command('wi-create', 'Create a work item', auth='devops',
                       mutates=True, confirmation=True, idempotent=False,
                       flags=[
                           schema_mod.flag('--type', value='<type>', summary='Work-item type', required=True),
                           schema_mod.flag('--title', value='<title>', summary='Title', required=True),
                           schema_mod.flag('--assign', value='@me|<email>', summary='Assignee'),
                           schema_mod.flag('--parent', value='<id>', summary='Parent work-item id'),
                           schema_mod.flag('--field', value='<path=value>', summary='Set a field', repeatable=True),
                           schema_mod.flag('--confirm', summary='Skip confirmation prompt'),
                       ]),
    schema_mod.command('wi-update', 'Update a work item', auth='devops',
                       mutates=True, confirmation=True, idempotent=True,
                       flags=[
                           schema_mod.flag('<id>', summary='Work-item id (positional)', required=True),
                           schema_mod.flag('--state', value='<state>', summary='New state'),
                           schema_mod.flag('--title', value='<title>', summary='New title'),
                           schema_mod.flag('--field', value='<path=value>', summary='Set a field', repeatable=True),
                           schema_mod.flag('--confirm', summary='Skip confirmation prompt'),
                       ]),
    schema_mod.command('wi-comment', 'Add a comment to a work item', auth='devops',
                       mutates=True, confirmation=True, idempotent=False,
                       flags=[
                           schema_mod.flag('<id>', summary='Work-item id (positional)', required=True),
                           schema_mod.flag('--text', value='<text>', summary='Comment body', required=True),
                           _API_VERSION,
                           schema_mod.flag('--confirm', summary='Skip confirmation prompt'),
                       ]),
    schema_mod.command('wi-link', 'Add a link/relation to a work item', auth='devops',
                       mutates=True, confirmation=True, idempotent=False,
                       flags=[
                           schema_mod.flag('<id>', summary='Work-item id (positional)', required=True),
                           schema_mod.flag('--target', value='<id>', summary='Target work-item id', required=True),
                           schema_mod.flag('--rel', value='<name>', summary='Link type (default related; e.g. parent/child/successor)'),
                           _API_VERSION,
                           schema_mod.flag('--confirm', summary='Skip confirmation prompt'),
                       ]),
    schema_mod.command('wi-unlink', 'Remove a link/relation from a work item', auth='devops',
                       mutates=True, confirmation=True, idempotent=True,
                       flags=[
                           schema_mod.flag('<id>', summary='Work-item id (positional)', required=True),
                           schema_mod.flag('--target', value='<id>', summary='Linked target id to remove', required=True),
                           schema_mod.flag('--rel', value='<name>', summary='Narrow to a link type'),
                           _API_VERSION,
                           schema_mod.flag('--confirm', summary='Skip confirmation prompt'),
                       ]),
    schema_mod.command('wi-delete', 'Delete a work item', auth='devops',
                       mutates=True, confirmation=True, idempotent=True,
                       flags=[
                           schema_mod.flag('<id>', summary='Work-item id (positional)', required=True),
                           schema_mod.flag('--destroy', summary='Permanent delete (bypass recycle bin)'),
                           _API_VERSION,
                           schema_mod.flag('--confirm', summary='Skip confirmation prompt'),
                       ]),
    schema_mod.command('repos', 'List repositories', auth='devops', aliases=['repositories'],
                       flags=[_ALL, _PRETTY]),
    schema_mod.command('prs', 'List pull requests or show one by id', auth='devops',
                       flags=[
                           schema_mod.flag('<id>', summary='Pull-request id to show (positional)'),
                           schema_mod.flag('--repo', value='<name>', summary='Scope to one repository'),
                           schema_mod.flag('--status', value='active|completed|abandoned|all', summary='Status filter (default active)'),
                           schema_mod.flag('--top', value='<n>', summary='Cap results (default 50)'),
                           _ALL, _API_VERSION, _PRETTY,
                       ]),
    schema_mod.command('pipelines', 'List pipeline definitions', auth='devops',
                       flags=[_ALL, _PRETTY]),
    schema_mod.command('runs', 'List recent pipeline runs (builds)', auth='devops',
                       flags=[
                           schema_mod.flag('--pipeline', value='<id>', summary='Filter to one definition'),
                           schema_mod.flag('--top', value='<n>', summary='Cap results (default 20)'),
                           _ALL, _API_VERSION, _PRETTY,
                       ]),
    schema_mod.command('refresh', 'Force a token refresh', auth='devops'),
    schema_mod.command('config', 'View or update configuration', mutates=True,
                       flags=[
                           schema_mod.flag('--profile', value='<alias>', summary='Pin owa-piggy profile'),
                           schema_mod.flag('--org', value='<org>', summary='Pin default organisation'),
                           schema_mod.flag('--project', value='<name>', summary='Pin default project'),
                           schema_mod.flag('--unset', value='<key>', summary='Remove one key', repeatable=True),
                           schema_mod.flag('--clear', summary='Remove all stored keys'),
                       ]),
]


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-ado', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled

    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] in ('--version', '-v'):
        print(f'owa-ado {__version__}')
        return 0

    debug_flag = False
    profile_override = org_override = project_override = ''
    is_config_cmd = _command_name(argv) == 'config'
    filtered = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--debug', '--verbose'):
            debug_flag = True
        elif a == '--profile' and not is_config_cmd:
            if i + 1 >= len(argv):
                raise UsageError('--profile requires a value')
            profile_override = argv[i + 1]
            i += 2
            continue
        elif a in ('--org', '-o') and not is_config_cmd:
            if i + 1 >= len(argv):
                raise UsageError(f'{a} requires a value')
            org_override = argv[i + 1]
            i += 2
            continue
        elif a in ('--project', '-P') and not is_config_cmd:
            if i + 1 >= len(argv):
                raise UsageError(f'{a} requires a value')
            project_override = argv[i + 1]
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
    cmd = schema_mod.resolve_alias(cmd, COMMAND_SCHEMA)

    help_rc = schema_mod.maybe_emit_subcommand_help(
        cmd, rest, tool='owa-ado', commands=COMMAND_SCHEMA,
    )
    if help_rc is not None:
        return help_rc

    config = config_mod.load_config()
    if debug_flag:
        config['debug'] = True
        _info('DEBUG: verbose logging enabled')
    if profile_override:
        config['owa_piggy_profile'] = profile_override
    if org_override:
        config['ado_org'] = org_override
    if project_override:
        config['ado_project'] = project_override

    if cmd == 'config':
        return cmd_config(rest, config)
    if cmd == 'refresh':
        return cmd_refresh(rest, config)

    if cmd not in AUTHED_COMMANDS:
        raise UsageError(f"Unknown command: {cmd}. Run 'owa-ado help' for usage.")

    schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)

    org = _resolve_org(config)
    base = auth_mod.org_base(org)
    # Fail fast on a missing project before touching the broker - every
    # authed command except `projects` is project-scoped, so an absent
    # project is a usage error, not an auth failure.
    if cmd != 'projects':
        _resolve_project(config)
    token = auth_mod.setup_auth(config, debug=_debug_enabled(config))

    dispatch = {
        'projects': cmd_projects,
        'sprints': cmd_sprints,
        'wi': cmd_wi,
        'wi-create': cmd_wi_create,
        'wi-update': cmd_wi_update,
        'wi-comment': cmd_wi_comment,
        'wi-link': cmd_wi_link,
        'wi-unlink': cmd_wi_unlink,
        'wi-delete': cmd_wi_delete,
        'repos': cmd_repos,
        'prs': cmd_prs,
        'pipelines': cmd_pipelines,
        'runs': cmd_runs,
    }
    return dispatch[cmd](rest, config, token, base)


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-ado',
        sys.argv[1:] if argv is None else argv,
        _main,
    )
