"""HaloITSM REST helpers. Authenticated calls go to the tenant API; signed
CDN links and inline-image capability URLs are fetched without the bearer."""

from urllib.parse import urlencode

from owa_core import http


def _get(base, path, token, params=None, *, debug=False):
    query = f'?{urlencode(params)}' if params else ''
    return http.request('GET', f'{base}/api/{path}{query}', token=token, debug=debug).json


def get_ticket(base, token, ticket_id, *, debug=False):
    return _get(base, f'Tickets/{ticket_id}', token, {'includedetails': 'true'}, debug=debug)


def get_actions(base, token, ticket_id, *, include_system=False, debug=False):
    params = {'ticket_id': ticket_id, 'includehtmlnote': 'true', 'includeattachments': 'true'}
    if not include_system:
        params['excludesys'] = 'true'
    return _get(base, 'Actions', token, params, debug=debug)


def get_attachments(base, token, ticket_id, *, debug=False):
    return _get(base, 'Attachment', token, {'ticket_id': ticket_id}, debug=debug)


def get_statuses(base, token, *, debug=False):
    return _get(base, 'Status', token, debug=debug)


def attachment_link(base, token, attachment_id, *, debug=False):
    """Halo answers with {"link": <signed CDN url>}, not the bytes."""
    return (_get(base, f'Attachment/{attachment_id}', token, debug=debug) or {}).get('link')


def fetch_unauthenticated(url, *, debug=False):
    # ponytail: whole file in memory; stream to disk if tickets carry huge attachments
    return http.request_unauthenticated('GET', url, debug=debug).bytes
