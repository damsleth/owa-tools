"""ServiceNow Table API transport for captured SWODP sessions."""

from __future__ import annotations

import json
from urllib.parse import urlencode

from owa_core import http
from owa_core.errors import AuthExpiredError, InternalError

from .session import SwodpSession


def table_url(session: SwodpSession, table: str, *, sys_id=None, params=None):
    path = f"https://{session.host}/api/now/table/{table}"
    if sys_id:
        path += f"/{sys_id}"
    return f"{path}?{urlencode(params)}" if params else path


def request(session, method, table, *, sys_id=None, params=None, body=None, debug=False):
    headers = {
        "X-UserToken": session.user_token,
        "Cookie": session.cookie_header,
        "Accept": "application/json",
    }
    raw_body = None
    if body is not None:
        raw_body = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        response = http.request_unauthenticated(
            method,
            table_url(session, table, sys_id=sys_id, params=params),
            body=raw_body,
            headers=headers,
            debug=debug,
        )
    except AuthExpiredError as exc:
        raise AuthExpiredError(
            "SWODP session expired",
            remediation=f"Run: owa-swodp setup --instance {session.instance}",
            cause=exc,
        ) from exc
    if not response.bytes:
        return {}
    content_type = ""
    for key, value in response.headers.items():
        if key.lower() == "content-type":
            content_type = value.lower()
            break
    if "html" in content_type:
        raise AuthExpiredError(
            "SWODP session redirected to sign-in",
            remediation=f"Run: owa-swodp setup --instance {session.instance}",
        )
    try:
        payload = json.loads(response.bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InternalError("SWODP response was not valid JSON", cause=exc) from exc
    if not isinstance(payload, dict) or "result" not in payload:
        raise InternalError("SWODP response lacked a result field")
    return payload["result"]
