"""Pure transforms over Azure DevOps REST payloads.

No I/O - normalizers flatten the verbose REST shapes into stable, thin
dicts (the JSON contract owa-ado emits) and the WIQL builder assembles a
query string from CLI flags. Kept separate from api.py so it is trivially
unit-testable without a network or token.
"""

# Compact field set requested for work-item list/show, so the JSON stays
# small and the same keys appear whether listing or showing.
WI_FIELDS = (
    'System.Id',
    'System.WorkItemType',
    'System.Title',
    'System.State',
    'System.AssignedTo',
    'System.IterationPath',
    'System.AreaPath',
    'System.Tags',
    'System.ChangedDate',
)


def _identity(value):
    """DevOps identity fields are sometimes a bare string, sometimes a
    {displayName, uniqueName, ...} dict. Collapse to displayName/email."""
    if isinstance(value, dict):
        return value.get('displayName') or value.get('uniqueName') or value.get('id')
    return value


def normalize_project(p):
    if not isinstance(p, dict):
        return {}
    return {
        'id': p.get('id'),
        'name': p.get('name'),
        'description': p.get('description'),
        'state': p.get('state'),
        'visibility': p.get('visibility'),
        'lastUpdate': p.get('lastUpdateTime'),
        'url': p.get('url'),
    }


def normalize_iteration(it):
    if not isinstance(it, dict):
        return {}
    attrs = it.get('attributes') or {}
    return {
        'id': it.get('id'),
        'name': it.get('name'),
        'path': it.get('path'),
        'startDate': attrs.get('startDate'),
        'finishDate': attrs.get('finishDate'),
        'timeFrame': attrs.get('timeFrame'),
    }


def normalize_work_item(wi):
    if not isinstance(wi, dict):
        return {}
    fields = wi.get('fields') or {}
    return {
        'id': wi.get('id') or fields.get('System.Id'),
        'type': fields.get('System.WorkItemType'),
        'title': fields.get('System.Title'),
        'state': fields.get('System.State'),
        'assignedTo': _identity(fields.get('System.AssignedTo')),
        'iteration': fields.get('System.IterationPath'),
        'area': fields.get('System.AreaPath'),
        'tags': fields.get('System.Tags'),
        'changed': fields.get('System.ChangedDate'),
        'url': wi.get('url'),
    }


def normalize_repo(r):
    if not isinstance(r, dict):
        return {}
    return {
        'id': r.get('id'),
        'name': r.get('name'),
        'defaultBranch': (r.get('defaultBranch') or '').replace('refs/heads/', '') or None,
        'size': r.get('size'),
        'project': (r.get('project') or {}).get('name'),
        'webUrl': r.get('webUrl'),
        'disabled': r.get('isDisabled'),
    }


def normalize_pr(pr):
    if not isinstance(pr, dict):
        return {}
    return {
        'id': pr.get('pullRequestId'),
        'title': pr.get('title'),
        'status': pr.get('status'),
        'createdBy': _identity(pr.get('createdBy')),
        'repo': (pr.get('repository') or {}).get('name'),
        'sourceBranch': (pr.get('sourceRefName') or '').replace('refs/heads/', '') or None,
        'targetBranch': (pr.get('targetRefName') or '').replace('refs/heads/', '') or None,
        'isDraft': pr.get('isDraft'),
        'created': pr.get('creationDate'),
        'url': pr.get('url'),
    }


def normalize_pipeline(p):
    if not isinstance(p, dict):
        return {}
    return {
        'id': p.get('id'),
        'name': p.get('name'),
        'folder': p.get('folder'),
        'revision': p.get('revision'),
        'url': p.get('url') or (p.get('_links') or {}).get('web', {}).get('href'),
    }


def normalize_build(b):
    if not isinstance(b, dict):
        return {}
    return {
        'id': b.get('id'),
        'buildNumber': b.get('buildNumber'),
        'status': b.get('status'),
        'result': b.get('result'),
        'pipeline': (b.get('definition') or {}).get('name'),
        'branch': (b.get('sourceBranch') or '').replace('refs/heads/', '') or None,
        'requestedFor': _identity(b.get('requestedFor')),
        'queued': b.get('queueTime'),
        'finished': b.get('finishTime'),
    }


def _quote_wiql(value):
    """Escape a single-quoted WIQL literal."""
    return value.replace("'", "''")


def build_wiql(*, project=None, mine=False, state=None, wi_type=None,
               iteration=None):
    """Assemble a WIQL query from the common owa-ado filters.

    Selects only [System.Id] (the fields come from a follow-up batch get).
    Result-count limiting is done with the `$top` query parameter on the
    wiql POST, not in the query text - WIQL has no TOP clause (it raises
    TF51006 "missing FROM clause").
    """
    select = 'SELECT [System.Id]'
    clauses = []
    if project:
        clauses.append(f"[System.TeamProject] = '{_quote_wiql(project)}'")
    if mine:
        clauses.append('[System.AssignedTo] = @Me')
    if state:
        clauses.append(f"[System.State] = '{_quote_wiql(state)}'")
    if wi_type:
        clauses.append(f"[System.WorkItemType] = '{_quote_wiql(wi_type)}'")
    if iteration:
        clauses.append(f"[System.IterationPath] = '{_quote_wiql(iteration)}'")
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    return f'{select} FROM workitems{where} ORDER BY [System.ChangedDate] DESC'
