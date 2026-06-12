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
    lines = [f"#{wi.get('id')} {wi.get('title') or '(no title)'} [{wi.get('type')}]"]
    for label, key in (
        ('state', 'state'), ('assignedTo', 'assignedTo'),
        ('iteration', 'iteration'), ('area', 'area'),
        ('tags', 'tags'), ('changed', 'changed'), ('url', 'url'),
    ):
        if wi.get(key):
            lines.append(f"  {label}: {wi.get(key)}")
    return '\n'.join(lines)


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


def format_builds(items):
    rows = [('id', 'buildNumber', 'status', 'result', 'pipeline', 'branch')]
    for b in items:
        rows.append((
            b.get('id'), b.get('buildNumber'), b.get('status'),
            b.get('result'), _truncate(b.get('pipeline') or '', 30), b.get('branch'),
        ))
    return _table(rows)
