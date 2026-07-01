"""Pure-transform coverage for owa_ado.resources (no I/O)."""
from owa_ado import resources as res


def test_normalize_project():
    out = res.normalize_project({
        'id': 'p1', 'name': 'NOCOS', 'state': 'wellFormed',
        'visibility': 'private', 'lastUpdateTime': '2022', 'url': 'u',
        'description': 'd',
    })
    assert out == {
        'id': 'p1', 'name': 'NOCOS', 'description': 'd', 'state': 'wellFormed',
        'visibility': 'private', 'lastUpdate': '2022', 'url': 'u',
    }


def test_normalize_iteration_flattens_attributes():
    out = res.normalize_iteration({
        'id': 'i1', 'name': 'CD 1', 'path': 'NOCOS\\CD 1',
        'attributes': {'startDate': 'a', 'finishDate': 'b', 'timeFrame': 'current'},
    })
    assert out['timeFrame'] == 'current'
    assert out['startDate'] == 'a' and out['finishDate'] == 'b'


def test_normalize_work_item_pulls_fields_and_identity():
    out = res.normalize_work_item({
        'id': 12, 'url': 'u',
        'fields': {
            'System.WorkItemType': 'Task', 'System.Title': 'T',
            'System.State': 'Active',
            'System.AssignedTo': {'displayName': 'Kim', 'uniqueName': 'k@x'},
            'System.IterationPath': 'NOCOS\\CD 1',
        },
    })
    assert out['id'] == 12
    assert out['type'] == 'Task'
    assert out['assignedTo'] == 'Kim'
    assert out['iteration'] == 'NOCOS\\CD 1'


def test_identity_accepts_bare_string():
    out = res.normalize_work_item({'id': 1, 'fields': {'System.AssignedTo': 'plain'}})
    assert out['assignedTo'] == 'plain'


def test_normalize_repo_strips_refs_prefix():
    out = res.normalize_repo({
        'id': 'r', 'name': 'NOCOS', 'defaultBranch': 'refs/heads/main',
        'project': {'name': 'NOCOS'}, 'webUrl': 'w', 'size': 10,
    })
    assert out['defaultBranch'] == 'main'
    assert out['project'] == 'NOCOS'


def test_normalize_pr_strips_branch_prefixes():
    out = res.normalize_pr({
        'pullRequestId': 7, 'title': 'x', 'status': 'active',
        'createdBy': {'displayName': 'Kim'},
        'repository': {'name': 'NOCOS-Main'},
        'sourceRefName': 'refs/heads/feature', 'targetRefName': 'refs/heads/main',
    })
    assert out['id'] == 7
    assert out['sourceBranch'] == 'feature' and out['targetBranch'] == 'main'
    assert out['repo'] == 'NOCOS-Main'


def test_normalize_build():
    out = res.normalize_build({
        'id': 1, 'buildNumber': '20260611.1', 'status': 'completed',
        'result': 'succeeded', 'definition': {'name': 'CI'},
        'sourceBranch': 'refs/heads/main', 'requestedFor': {'displayName': 'Kim'},
    })
    assert out['pipeline'] == 'CI'
    assert out['branch'] == 'main'
    assert out['requestedFor'] == 'Kim'


def test_build_wiql_defaults_to_mine_and_orders():
    q = res.build_wiql(project='NOCOS', mine=True)
    assert q.startswith('SELECT [System.Id] FROM workitems WHERE ')
    assert "[System.TeamProject] = 'NOCOS'" in q
    assert '[System.AssignedTo] = @Me' in q
    assert q.endswith('ORDER BY [System.ChangedDate] DESC')
    # WIQL has no TOP clause; must never appear.
    assert 'TOP' not in q


def test_build_wiql_filters_and_escapes_quotes():
    q = res.build_wiql(project="O'Brien", state='Active', wi_type='Bug')
    assert "[System.TeamProject] = 'O''Brien'" in q
    assert "[System.State] = 'Active'" in q
    assert "[System.WorkItemType] = 'Bug'" in q


def test_build_wiql_no_filters_has_no_where():
    q = res.build_wiql()
    assert 'WHERE' not in q


def test_build_wiql_iteration_clause():
    # WIQL string literals take a literal backslash for IterationPath
    # separators - no backslash escaping (only single quotes are doubled).
    q = res.build_wiql(project='NOCOS', iteration='NOCOS\\Sprint 1')
    assert "[System.IterationPath] = 'NOCOS\\Sprint 1'" in q


def test_build_wiql_iteration_escapes_quotes():
    q = res.build_wiql(iteration="O'Brien\\Sprint 1")
    assert "[System.IterationPath] = 'O''Brien\\Sprint 1'" in q


def test_normalize_comment_flattens_identity_and_strips_html():
    out = res.normalize_comment({
        'id': 7, 'workItemId': 17054, 'text': '<p>Hi&amp;bye</p>',
        'createdBy': {'displayName': 'Kim'}, 'createdDate': '2026',
        'url': 'u',
    })
    assert out == {
        'id': 7, 'workItemId': 17054, 'text': 'Hi&bye',
        'createdBy': 'Kim', 'createdDate': '2026', 'url': 'u',
    }


def test_normalize_comment_non_dict():
    assert res.normalize_comment(None) == {}


def test_resolve_rel_friendly_and_passthrough():
    assert res.resolve_rel('parent') == 'System.LinkTypes.Hierarchy-Reverse'
    assert res.resolve_rel('RELATED') == 'System.LinkTypes.Related'
    # An unknown / already-qualified rel is used verbatim.
    assert res.resolve_rel('System.LinkTypes.Custom') == 'System.LinkTypes.Custom'


def test_normalize_variable_group_masks_secrets():
    out = res.normalize_variable_group({
        'id': 3, 'name': 'shared', 'type': 'Vsts', 'description': 'd',
        'variables': {'URL': {'value': 'x'}, 'KEY': {'isSecret': True}},
        'modifiedBy': {'displayName': 'Kim'}, 'modifiedOn': '2026',
    })
    assert out['variables'] == {'URL': 'x', 'KEY': '***'}
    assert out['modifiedBy'] == 'Kim'


def test_normalize_subresources_and_non_dict():
    assert res.normalize_variable_group(None) == {}
    assert res.normalize_task_group({'id': 1, 'name': 't', 'tasks': [{}, {}]})['tasks'] == 2
    assert res.normalize_task_group(None) == {}
    assert res.normalize_deployment_group({'id': 2, 'machineCount': 5})['machineCount'] == 5
    assert res.normalize_deployment_group(None) == {}
    assert res.normalize_environment({'id': 3, 'name': 'prod'})['name'] == 'prod'
    assert res.normalize_environment(None) == {}
    rel = res.normalize_release({'id': 9, 'name': 'R-9', 'status': 'active',
                                 'releaseDefinition': {'name': 'Deploy'},
                                 'createdBy': {'displayName': 'Ada'}})
    assert rel['definition'] == 'Deploy' and rel['createdBy'] == 'Ada'
    assert res.normalize_release(None) == {}
