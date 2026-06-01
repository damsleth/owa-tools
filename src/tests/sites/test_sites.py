"""Pure-function tests for owa_sites.sites (URL builders + normalizers)."""

from owa_sites import sites


def test_site_path():
    assert sites.site_path('owa-casa') == 'sites/owa-casa'
    assert sites.site_path('sites/owa-casa') == 'sites/owa-casa'
    assert sites.site_path('teams/Marketing') == 'teams/Marketing'
    assert sites.site_path('') == ''
    assert sites.site_path('/') == ''


def test_api_endpoint():
    assert sites.api_endpoint('owa-casa', 'web') == 'sites/owa-casa/_api/web'
    assert sites.api_endpoint('', 'web') == '_api/web'


def test_web_endpoint():
    assert sites.web_endpoint('owa-casa') == 'sites/owa-casa/_api/web?$select=Title,Url,Id,Created'


def test_lists_endpoint():
    assert sites.lists_endpoint('') == '_api/web/lists?$select=Title,Id,ItemCount,BaseTemplate,Hidden'


def test_list_items_endpoint():
    ep = sites.list_items_endpoint('owa-casa', 'Documents', select='Title', top=10)
    assert ep.startswith("sites/owa-casa/_api/web/lists/getbytitle('Documents')/items?")
    assert '$select=Title' in ep
    assert '$top=10' in ep


def test_folder_files_endpoint_encodes_alias():
    ep = sites.folder_files_endpoint('owa-casa', '/sites/owa-casa/Shared Documents')
    assert 'web/GetFolderByServerRelativePath(DecodedUrl=@a1)/Files?@a1=' in ep
    assert '%2Fsites%2Fowa-casa%2FShared%20Documents' in ep


def test_search_endpoint():
    ep = sites.search_endpoint('budget', rowlimit=5)
    assert ep.startswith('_api/search/query?querytext=')
    assert 'rowlimit=5' in ep
    assert 'selectproperties=' in ep


def test_normalize_web():
    assert sites.normalize_web({'Title': 'T', 'Url': 'u', 'Id': 'i', 'Created': 'c'}) == {
        'title': 'T', 'url': 'u', 'id': 'i', 'created': 'c',
    }


def test_normalize_lists_filters_hidden():
    payload = {'value': [
        {'Title': 'Documents', 'Id': 'l1', 'ItemCount': 5, 'BaseTemplate': 101, 'Hidden': False},
        {'Title': 'Sys', 'Id': 'l2', 'ItemCount': 0, 'BaseTemplate': 100, 'Hidden': True},
    ]}
    visible = sites.normalize_lists(payload)
    assert [x['title'] for x in visible] == ['Documents']
    assert visible[0]['itemCount'] == 5
    assert len(sites.normalize_lists(payload, include_hidden=True)) == 2


def test_normalize_lists_accepts_bare_list():
    rows = sites.normalize_lists([{'Title': 'A', 'Hidden': False}])
    assert rows[0]['title'] == 'A'


def test_normalize_file():
    f = sites.normalize_file({
        'Name': 'a.docx', 'ServerRelativeUrl': '/x/a.docx', 'Length': '123',
        'TimeLastModified': 't', 'UniqueId': 'u',
    })
    assert f == {
        'name': 'a.docx', 'serverRelativeUrl': '/x/a.docx', 'length': 123,
        'modified': 't', 'uniqueId': 'u',
    }


def test_normalize_item_strips_odata_envelope():
    item = {'Id': 1, 'Title': 'X', 'odata.etag': '"1"', '@odata.id': 'foo'}
    assert sites.normalize_item(item) == {'Id': 1, 'Title': 'X'}


def test_flatten_search_rows():
    payload = {'PrimaryQueryResult': {'RelevantResults': {'Table': {'Rows': [
        {'Cells': [{'Key': 'Title', 'Value': 'Doc'}, {'Key': 'Path', 'Value': 'http://x'}]},
    ]}}}}
    assert sites.flatten_search_rows(payload) == [{'Title': 'Doc', 'Path': 'http://x'}]


def test_flatten_search_rows_empty():
    assert sites.flatten_search_rows({}) == []
