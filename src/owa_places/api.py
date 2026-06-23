"""SchedulingB2 HTTP helper for owa-places."""

from urllib.parse import urlencode

from owa_core import http

SCHEDULING_PATH = 'SchedulingB2/api/v1.0/me/initmeetinglocations'
DEFAULT_CV = 'owa-tools-places-v1'


def scheduling_post(base, access_token, body=None, *, cv=DEFAULT_CV, debug=False):
    query = urlencode({'cv': cv})
    url = f'{base.rstrip("/")}/{SCHEDULING_PATH}?{query}'
    return http.request('POST', url, token=access_token, body=body or {}, debug=debug).json
