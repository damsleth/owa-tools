"""Outlook REST HTTP helper. Same shape as owa-people/owa-cal.

Outlook REST speaks PascalCase; `camel` lower-cases response keys so the
normalizers keep reading the camelCase shape they were written against."""

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


def camel(obj):
    """Lower-case the first letter of every dict key, recursively.
    Idempotent on camelCase input."""
    if isinstance(obj, dict):
        return {k[:1].lower() + k[1:]: camel(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [camel(v) for v in obj]
    return obj
