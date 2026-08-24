"""Pure transforms over Azure DevOps REST payloads.

No I/O - normalizers flatten the verbose REST shapes into stable, thin
dicts (the JSON contract owa-ado emits) and the WIQL builder assembles a
query string from CLI flags. Kept separate from api.py so it is trivially
unit-testable without a network or token.
"""
import html
import posixpath
import re

# Friendly link-type names mapped to the DevOps relation reference name.
# `--rel <name>` on wi-link/wi-unlink accepts either a friendly key here or
# a fully-qualified rel string (used verbatim when it isn't a known key).
LINK_RELS = {
    'parent': 'System.LinkTypes.Hierarchy-Reverse',
    'child': 'System.LinkTypes.Hierarchy-Forward',
    'related': 'System.LinkTypes.Related',
    'predecessor': 'System.LinkTypes.Dependency-Reverse',
    'successor': 'System.LinkTypes.Dependency-Forward',
    'duplicate': 'System.LinkTypes.Duplicate-Forward',
    'duplicate-of': 'System.LinkTypes.Duplicate-Reverse',
}


def resolve_rel(name):
    """Map a friendly link name to its rel string; pass dotted names through."""
    key = (name or '').strip()
    return LINK_RELS.get(key.lower(), key)

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


def _strip_html(value):
    """Turn ADO's HTML description into plain text. Drop tags, unescape
    entities, collapse whitespace. Not a real parser - good enough for a CLI."""
    if not value:
        return None
    text = re.sub(r'<[^>]+>', ' ', value)
    return re.sub(r'\s+', ' ', html.unescape(text)).strip() or None


def work_item_attachments(wi):
    """Pull attachment {name, url} pairs from a work item's relations
    (requires the payload to have been fetched with $expand=relations)."""
    out = []
    for r in (wi.get('relations') or []):
        if r.get('rel') == 'AttachedFile':
            out.append({
                'name': (r.get('attributes') or {}).get('name'),
                'url': r.get('url'),
            })
    return out


def normalize_work_item_detailed(wi, *, attachments=False):
    """The thin work-item dict plus the description (HTML stripped), and with
    attachments=True the attachment urls too."""
    item = normalize_work_item(wi)
    if not item:
        return item
    fields = wi.get('fields') or {}
    item['description'] = _strip_html(fields.get('System.Description'))
    if attachments:
        item['attachments'] = work_item_attachments(wi)
    return item


def normalize_comment(c):
    if not isinstance(c, dict):
        return {}
    return {
        'id': c.get('id'),
        'workItemId': c.get('workItemId'),
        'text': _strip_html(c.get('text')) or c.get('text'),
        'createdBy': _identity(c.get('createdBy')),
        'createdDate': c.get('createdDate'),
        'url': c.get('url'),
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


def normalize_variable_group(g):
    """Library variable group. Non-secret values pass through; secrets
    (isSecret, whose value the API withholds) render as '***' so the shape
    is uniform and no secret is implied to be empty."""
    if not isinstance(g, dict):
        return {}
    variables = g.get('variables') or {}
    return {
        'id': g.get('id'),
        'name': g.get('name'),
        'description': g.get('description'),
        'type': g.get('type'),
        'variables': {
            k: ('***' if (v or {}).get('isSecret') else (v or {}).get('value'))
            for k, v in variables.items()
        },
        'modifiedBy': _identity(g.get('modifiedBy')),
        'modifiedOn': g.get('modifiedOn'),
    }


def normalize_task_group(t):
    if not isinstance(t, dict):
        return {}
    return {
        'id': t.get('id'),
        'name': t.get('name'),
        'description': t.get('description'),
        'tasks': len(t.get('tasks') or []),
        'modifiedBy': _identity(t.get('modifiedBy')),
        'modifiedOn': t.get('modifiedOn'),
    }


def normalize_deployment_group(d):
    if not isinstance(d, dict):
        return {}
    return {
        'id': d.get('id'),
        'name': d.get('name'),
        'description': d.get('description'),
        'machineCount': d.get('machineCount'),
    }


def normalize_environment(e):
    if not isinstance(e, dict):
        return {}
    return {
        'id': e.get('id'),
        'name': e.get('name'),
        'description': e.get('description'),
        'createdBy': _identity(e.get('createdBy')),
    }


def normalize_release(r):
    if not isinstance(r, dict):
        return {}
    return {
        'id': r.get('id'),
        'name': r.get('name'),
        'status': r.get('status'),
        'definition': (r.get('releaseDefinition') or {}).get('name'),
        'createdBy': _identity(r.get('createdBy')),
        'createdOn': r.get('createdOn'),
    }


def normalize_wiki(w):
    if not isinstance(w, dict):
        return {}
    return {
        'id': w.get('id'),
        'name': w.get('name'),
        'type': w.get('type'),
        'mappedPath': w.get('mappedPath'),
        'remoteUrl': w.get('remoteUrl'),
        'url': w.get('url'),
    }


def normalize_wiki_page(p):
    """Thin wiki-page dict. `id`/`content`/`subPages` are only present when
    the REST call asked for them (page-by-id, includeContent, recursionLevel),
    so they are added only when the payload carries them - the shape stays
    honest about what was fetched. subPages recurse for tree listings."""
    if not isinstance(p, dict):
        return {}
    out = {
        'path': p.get('path'),
        'order': p.get('order'),
        'isParentPage': p.get('isParentPage'),
        'gitItemPath': p.get('gitItemPath'),
        'url': p.get('remoteUrl') or p.get('url'),
    }
    if p.get('id') is not None:
        out['id'] = p['id']
    if p.get('subPages'):
        out['subPages'] = [normalize_wiki_page(s) for s in p['subPages']]
    if p.get('content') is not None:
        out['content'] = p['content']
    return out


# --- Wiki ToC macros -------------------------------------------------------
# Azure DevOps renders two special tokens the raw Markdown keeps literal:
#   [[_TOC_]]   table of contents from the page's own headings
#   [[_TOSP_]]  table of subpages (the full descendant tree)
# For an offline copy these are expanded into real Markdown lists so the
# index/section pages are actually navigable in a codebase viewer.

TOC_TOKEN = '[[_TOC_]]'
TOSP_TOKEN = '[[_TOSP_]]'


def page_title(node):
    """Human display name of a wiki page: the leaf of its `path` (which keeps
    spaces), not the dash-encoded `gitItemPath`."""
    path = (node.get('path') or '').rstrip('/')
    return path.rsplit('/', 1)[-1] or '(untitled)'


def _gh_anchor(text, seen):
    """GitHub-flavoured heading anchor: lowercase, punctuation dropped, spaces
    to dashes, with -1/-2 suffixes for duplicates in document order.

    # ponytail: GH approximation, not ADO's exact scheme - right for a copy
    browsed on GitHub / in an IDE preview; revisit if links must resolve in
    the ADO renderer itself."""
    a = re.sub(r'\s+', '-', re.sub(r'[^\w\s-]', '', text.strip().lower()))
    n = seen.get(a, 0)
    seen[a] = n + 1
    return a if not n else f'{a}-{n}'


def extract_headings(content):
    """[(level, text)] for ATX headings, skipping fenced code blocks. ADO
    renders `##NoSpace` as a heading, so the space after the hashes is
    optional; a trailing run of `#` (closing ATX) is stripped."""
    out = []
    fence = None
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(('```', '~~~')):
            marker = stripped[:3]
            if fence is None:
                fence = marker
            elif stripped.startswith(fence):
                fence = None
            continue
        if fence is not None:
            continue
        m = re.match(r'(#{1,6})\s*(\S.*?)\s*#*$', line)
        if m:
            out.append((len(m.group(1)), m.group(2).strip()))
    return out


def render_toc(content):
    """A nested bullet list linking the page's headings. Nesting is *relative*
    (stack-based), matching ADO: each strictly-deeper heading indents one more
    level, so inconsistent absolute levels (a `#` after a `##`) still render as
    siblings rather than misnested - the visual depth is tree depth, not the
    hash count."""
    headings = extract_headings(content)
    if not headings:
        return ''
    seen = {}
    stack = []  # heading levels of the current ancestor chain
    lines = []
    for level, text in headings:
        while stack and stack[-1] >= level:
            stack.pop()
        lines.append(f'{"  " * len(stack)}- [{text}](#{_gh_anchor(text, seen)})')
        stack.append(level)
    return '\n'.join(lines)


def render_tosp(node):
    """A nested bullet list of every descendant page, each linked by a path
    relative to this page's own file so the links resolve on disk."""
    cur_dir = posixpath.dirname((node.get('gitItemPath') or '').lstrip('/'))
    lines = []

    def walk(children, depth):
        for child in children:
            git = (child.get('gitItemPath') or '').lstrip('/')
            subs = child.get('subPages') or []
            if git.endswith('.md'):
                rel = posixpath.relpath(git, cur_dir) if cur_dir else git
                lines.append(f'{"  " * depth}- [{page_title(child)}]({rel})')
                walk(subs, depth + 1)
            else:
                walk(subs, depth)  # folder-only node: keep its children inline

    walk(node.get('subPages') or [], 0)
    return '\n'.join(lines)


def expand_wiki_macros(content, node):
    """Replace [[_TOC_]] / [[_TOSP_]] tokens in a page with generated lists.
    TOC is computed from the original content so an injected subpage list
    can't be mistaken for headings."""
    if not content:
        return content
    toc = render_toc(content) if TOC_TOKEN in content else None
    if TOSP_TOKEN in content:
        content = content.replace(TOSP_TOKEN, render_tosp(node))
    if toc is not None:
        content = content.replace(TOC_TOKEN, toc)
    return content


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
