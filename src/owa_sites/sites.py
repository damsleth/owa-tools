"""SharePoint REST URL builders + response normalizers for owa-sites.

SharePoint REST returns PascalCase; we normalize to a stable lowercase wire
shape on read. URL builders assemble the `_api/...` paths relative to the
`https://{host}` base (the site segment, if any, is prefixed).
"""
import urllib.parse


def _q(value):
    return urllib.parse.quote(value, safe='')


def site_path(site):
    """Normalize a --site value to a server-relative site segment.

    Accepts a bare name (`owa-casa` -> `sites/owa-casa`), an explicit path
    (`sites/owa-casa` / `teams/x` -> unchanged), a full SharePoint URL
    (`https://host/sites/owa-casa` -> `sites/owa-casa`), or empty/`/` for the
    root site (-> '' so endpoints hang off `_api/...` directly).
    """
    s = (site or '').strip()
    if s.startswith(('http://', 'https://')):
        # A pasted site URL: keep only the server-relative path. The host is
        # the tenant SharePoint host (already the `base`), so we discard it.
        s = urllib.parse.urlsplit(s).path
    s = s.strip().strip('/')
    if not s:
        return ''
    if s.startswith(('sites/', 'teams/')):
        return s
    return f'sites/{s}'


def api_endpoint(site, suffix):
    """Join the site segment with an `_api/<suffix>` path."""
    sp = site_path(site)
    prefix = f'{sp}/' if sp else ''
    return f'{prefix}_api/{suffix}'


def _odata_params(*, select='', filter='', orderby='', expand='', top=0):
    """Build the encoded $-param list shared by the collection endpoints."""
    params = []
    if select:
        params.append(f'$select={_q(select)}')
    if filter:
        params.append(f'$filter={_q(filter)}')
    if orderby:
        params.append(f'$orderby={_q(orderby)}')
    if expand:
        params.append(f'$expand={_q(expand)}')
    if top:
        params.append(f'$top={int(top)}')
    return params


def web_endpoint(site):
    return api_endpoint(site, 'web?$select=Title,Url,Id,Created')


def lists_endpoint(site, filter='', orderby='', expand=''):
    suffix = 'web/lists?$select=Title,Id,ItemCount,BaseTemplate,Hidden'
    extra = _odata_params(filter=filter, orderby=orderby, expand=expand)
    if extra:
        suffix += '&' + '&'.join(extra)
    return api_endpoint(site, suffix)


def list_items_endpoint(site, list_title, select='', top=0, filter='', orderby='', expand=''):
    suffix = f"web/lists/getbytitle('{_q(list_title)}')/items"
    params = _odata_params(
        select=select, filter=filter, orderby=orderby, expand=expand, top=top,
    )
    if params:
        suffix += '?' + '&'.join(params)
    return api_endpoint(site, suffix)


def list_item_endpoint(site, list_title, item_id, select='', expand=''):
    """Address a single list item by its integer Id."""
    suffix = f"web/lists/getbytitle('{_q(list_title)}')/items({int(item_id)})"
    params = _odata_params(select=select, expand=expand)
    if params:
        suffix += '?' + '&'.join(params)
    return api_endpoint(site, suffix)


def file_by_id_endpoint(site, unique_id):
    """Address a single file (drive item) by its UniqueId GUID."""
    return api_endpoint(site, f"web/GetFileById('{_q(unique_id)}')")


def folder_files_endpoint(site, server_relative_folder):
    alias = _q(f"'{server_relative_folder}'")
    return api_endpoint(site, f'web/GetFolderByServerRelativePath(DecodedUrl=@a1)/Files?@a1={alias}')


def search_endpoint(query, rowlimit=20, select_props='Title,Path,Author,LastModifiedTime'):
    qt = _q(f"'{query}'")
    sp = _q(f"'{select_props}'")
    return f'_api/search/query?querytext={qt}&rowlimit={int(rowlimit)}&selectproperties={sp}'


def _values(payload):
    if isinstance(payload, dict) and isinstance(payload.get('value'), list):
        return payload['value']
    if isinstance(payload, list):
        return payload
    return []


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_web(web):
    web = web or {}
    return {
        'title': web.get('Title'),
        'url': web.get('Url'),
        'id': web.get('Id'),
        'created': web.get('Created'),
    }


def normalize_list(lst):
    return {
        'title': lst.get('Title'),
        'id': lst.get('Id'),
        'itemCount': _int(lst.get('ItemCount')),
        'baseTemplate': lst.get('BaseTemplate'),
        'hidden': bool(lst.get('Hidden')),
    }


def normalize_lists(payload, include_hidden=False):
    rows = [normalize_list(x) for x in _values(payload)]
    if include_hidden:
        return rows
    return [r for r in rows if not r['hidden']]


def normalize_file(f):
    return {
        'name': f.get('Name'),
        'serverRelativeUrl': f.get('ServerRelativeUrl'),
        'length': _int(f.get('Length')),
        'modified': f.get('TimeLastModified'),
        'uniqueId': f.get('UniqueId'),
    }


def normalize_files(payload):
    return [normalize_file(f) for f in _values(payload)]


def normalize_item(item):
    """A list item, with the OData envelope keys stripped (nometadata still
    emits `odata.etag` / `odata.id`)."""
    return {
        k: v for k, v in item.items()
        if not k.startswith('odata.') and not k.startswith('@')
    }


def normalize_items(payload):
    return [normalize_item(x) for x in _values(payload)]


def flatten_search_rows(payload):
    """Flatten SharePoint search `Rows[].Cells[{Key,Value}]` into flat dicts."""
    table = (
        ((payload or {}).get('PrimaryQueryResult') or {})
        .get('RelevantResults', {})
        .get('Table', {})
    )
    rows = table.get('Rows') or []
    out = []
    for row in rows:
        cells = row.get('Cells') or []
        out.append({c.get('Key'): c.get('Value') for c in cells if c.get('Key')})
    return out
