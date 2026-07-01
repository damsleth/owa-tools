"""Human-readable rendering for `--pretty`. JSON is the default surface;
these helpers are only for terminal-facing output."""
from owa_core.format import truncate as _truncate


def _date(s):
    return (s or '')[:10] if s else '-'


def _table(rows):
    """rows[0] is the header tuple; widths auto-fit. Cells stringified."""
    if len(rows) <= 1:
        return '(empty)'
    rows = [tuple('' if c is None else str(c) for c in r) for r in rows]
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return '\n'.join(
        '  '.join(c.ljust(w) for c, w in zip(r, widths)).rstrip()
        for r in rows
    )


def format_projects(items):
    rows = [('name', 'state', 'visibility', 'id')]
    for p in items:
        rows.append((p.get('name'), p.get('state'), p.get('visibility'), p.get('id')))
    return _table(rows)


def format_iterations(items):
    rows = [('name', 'timeframe', 'start', 'finish', 'path')]
    for it in items:
        rows.append((
            it.get('name'), it.get('timeFrame'),
            _date(it.get('startDate')), _date(it.get('finishDate')),
            it.get('path'),
        ))
    return _table(rows)


def format_work_items(items):
    rows = [('id', 'type', 'state', 'assignedTo', 'title')]
    for wi in items:
        rows.append((
            wi.get('id'), wi.get('type'), wi.get('state'),
            _truncate(wi.get('assignedTo') or '-', 20),
            _truncate(wi.get('title') or '', 60),
        ))
    return _table(rows)


def format_work_item(wi):
    if not wi:
        return '(no work item)'
    # Key on its own line, value below it, blank line between fields.
    blocks = [f"#{wi.get('id')} {wi.get('title') or '(no title)'} [{wi.get('type')}]"]
    for label, key in (
        ('state', 'state'), ('assignedTo', 'assignedTo'),
        ('iteration', 'iteration'), ('area', 'area'),
        ('tags', 'tags'), ('changed', 'changed'), ('url', 'url'),
        ('description', 'description'),
    ):
        if wi.get(key):
            blocks.append(f"{label}:\n{wi.get(key)}")
    atts = wi.get('attachments') or []
    if atts:
        lines = [f"{a.get('name')} -> {a.get('url')}" for a in atts]
        blocks.append('attachments:\n' + '\n'.join(lines))
    return '\n\n'.join(blocks)


def format_repos(items):
    rows = [('name', 'defaultBranch', 'project', 'id')]
    for r in items:
        rows.append((r.get('name'), r.get('defaultBranch'), r.get('project'), r.get('id')))
    return _table(rows)


def format_prs(items):
    rows = [('id', 'status', 'repo', 'createdBy', 'title')]
    for pr in items:
        rows.append((
            pr.get('id'), pr.get('status'), pr.get('repo'),
            _truncate(pr.get('createdBy') or '-', 18),
            _truncate(pr.get('title') or '', 50),
        ))
    return _table(rows)


def format_pr(pr):
    if not pr:
        return '(no pull request)'
    lines = [f"!{pr.get('id')} {pr.get('title') or '(no title)'} [{pr.get('status')}]"]
    for label, key in (
        ('repo', 'repo'), ('createdBy', 'createdBy'),
        ('source', 'sourceBranch'), ('target', 'targetBranch'),
        ('draft', 'isDraft'), ('created', 'created'), ('url', 'url'),
    ):
        if pr.get(key) is not None:
            lines.append(f"  {label}: {pr.get(key)}")
    return '\n'.join(lines)


def format_pipelines(items):
    rows = [('id', 'name', 'folder')]
    for p in items:
        rows.append((p.get('id'), p.get('name'), p.get('folder')))
    return _table(rows)


def format_variable_groups(items):
    rows = [('id', 'name', 'type', 'vars', 'description')]
    for g in items:
        rows.append((
            g.get('id'), g.get('name'), g.get('type'),
            len(g.get('variables') or {}),
            _truncate(g.get('description') or '', 40),
        ))
    return _table(rows)


def format_variable_group(g):
    """Single variable group detail: header line then a variable/value table
    (secrets already masked upstream). The whole point of fetching one group."""
    head = f"{g.get('name')}  (id {g.get('id')}, type {g.get('type')})"
    lines = [head]
    if g.get('description'):
        lines.append(g['description'])
    variables = g.get('variables') or {}
    rows = [('variable', 'value')]
    for k in sorted(variables):
        rows.append((k, variables[k]))
    lines.append('')
    lines.append(_table(rows) if variables else '(no variables)')
    return '\n'.join(lines)


def format_task_groups(items):
    rows = [('id', 'name', 'tasks', 'modifiedBy')]
    for t in items:
        rows.append((t.get('id'), t.get('name'), t.get('tasks'),
                     _truncate(t.get('modifiedBy') or '-', 20)))
    return _table(rows)


def format_deployment_groups(items):
    rows = [('id', 'name', 'machines', 'description')]
    for d in items:
        rows.append((d.get('id'), d.get('name'), d.get('machineCount'),
                     _truncate(d.get('description') or '', 40)))
    return _table(rows)


def format_environments(items):
    rows = [('id', 'name', 'description')]
    for e in items:
        rows.append((e.get('id'), e.get('name'),
                     _truncate(e.get('description') or '', 50)))
    return _table(rows)


def format_releases(items):
    rows = [('id', 'name', 'status', 'definition', 'createdBy')]
    for r in items:
        rows.append((r.get('id'), r.get('name'), r.get('status'),
                     _truncate(r.get('definition') or '', 25),
                     _truncate(r.get('createdBy') or '-', 20)))
    return _table(rows)


def format_builds(items):
    rows = [('id', 'buildNumber', 'status', 'result', 'pipeline', 'branch')]
    for b in items:
        rows.append((
            b.get('id'), b.get('buildNumber'), b.get('status'),
            b.get('result'), _truncate(b.get('pipeline') or '', 30), b.get('branch'),
        ))
    return _table(rows)
