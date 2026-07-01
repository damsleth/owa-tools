"""Pretty-rendering coverage for owa_ado.format."""
from owa_ado import format as fmt


def test_format_projects_table_has_header_and_row():
    out = fmt.format_projects([{'name': 'NOCOS', 'state': 'wellFormed',
                                'visibility': 'private', 'id': 'p1'}])
    lines = out.splitlines()
    assert lines[0].split() == ['name', 'state', 'visibility', 'id']
    assert 'NOCOS' in lines[1]


def test_empty_table_renders_placeholder():
    assert fmt.format_projects([]) == '(empty)'
    assert fmt.format_repos([]) == '(empty)'


def test_format_work_item_view():
    out = fmt.format_work_item({
        'id': 12, 'title': 'T', 'type': 'Task', 'state': 'Active',
        'assignedTo': 'Kim', 'url': 'u',
    })
    assert out.startswith('#12 T [Task]')
    assert 'state:\nActive' in out
    assert 'assignedTo:\nKim' in out


def test_format_work_item_handles_missing():
    assert fmt.format_work_item({}) == '(no work item)'


def test_format_work_items_truncates_long_title():
    out = fmt.format_work_items([{'id': 1, 'type': 'Task', 'state': 'New',
                                  'assignedTo': 'X', 'title': 'y' * 100}])
    assert '…' in out


def test_format_pr_view_and_table():
    pr = {'id': 7, 'title': 'PR', 'status': 'active', 'repo': 'R',
          'createdBy': 'Kim', 'sourceBranch': 'f', 'targetBranch': 'main',
          'isDraft': False}
    assert fmt.format_pr(pr).startswith('!7 PR [active]')
    table = fmt.format_prs([pr])
    assert table.splitlines()[0].split() == ['id', 'status', 'repo', 'createdBy', 'title']


def test_format_pr_handles_missing():
    assert fmt.format_pr({}) == '(no pull request)'


def test_format_builds_and_pipelines_and_iterations():
    assert 'CI' in fmt.format_builds([{'id': 1, 'buildNumber': '1', 'status': 'completed',
                                       'result': 'succeeded', 'pipeline': 'CI', 'branch': 'main'}])
    assert 'Deploy' in fmt.format_pipelines([{'id': 9, 'name': 'Deploy', 'folder': '\\'}])
    assert 'CD 1' in fmt.format_iterations([{'name': 'CD 1', 'timeFrame': 'current',
                                             'startDate': '2024-04-05T00:00:00Z',
                                             'finishDate': '2024-12-31T00:00:00Z',
                                             'path': 'NOCOS\\CD 1'}])


def test_format_subresource_tables():
    assert 'shared' in fmt.format_variable_groups(
        [{'id': 3, 'name': 'shared', 'type': 'Vsts',
          'variables': {'A': 'x'}, 'description': 'd'}])
    assert 'tg' in fmt.format_task_groups(
        [{'id': 1, 'name': 'tg', 'tasks': 2, 'modifiedBy': 'Kim'}])
    assert 'dg' in fmt.format_deployment_groups(
        [{'id': 2, 'name': 'dg', 'machineCount': 5, 'description': 'd'}])
    assert 'prod' in fmt.format_environments([{'id': 3, 'name': 'prod', 'description': 'd'}])
    assert 'R-9' in fmt.format_releases(
        [{'id': 9, 'name': 'R-9', 'status': 'active', 'definition': 'Deploy', 'createdBy': 'Ada'}])
