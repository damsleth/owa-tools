"""Graph HTTP helper. Same shape as owa-people/owa-cal."""

from owa_core import http


def api_request(method, base, endpoint, access_token, body=None,
                extra_headers=None, debug=False):
    url = f'{base}/{endpoint.lstrip("/")}'
    headers = dict(extra_headers or {})
    return http.request(
        method, url, token=access_token, body=body, headers=headers, debug=debug,
    ).json


def api_post(base, endpoint, access_token, body=None, extra_headers=None, debug=False):
    return api_request('POST', base, endpoint, access_token,
                       body=body, extra_headers=extra_headers, debug=debug)
