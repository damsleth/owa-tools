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


def _send(session, method, url, *, body=None, content_type=None, debug=False):
    headers = {
        "X-UserToken": session.user_token,
        "Cookie": session.cookie_header,
        "Accept": "application/json",
    }
    if content_type:
        headers["Content-Type"] = content_type
    try:
        response = http.request_unauthenticated(
            method,
            url,
            body=body,
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
        return None
    response_type = ""
    for key, value in response.headers.items():
        if key.lower() == "content-type":
            response_type = value.lower()
            break
    if "html" in response_type:
        raise AuthExpiredError(
            "SWODP session redirected to sign-in",
            remediation=f"Run: owa-swodp setup --instance {session.instance}",
        )
    try:
        return json.loads(response.bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InternalError("SWODP response was not valid JSON", cause=exc) from exc


def request(session, method, table, *, sys_id=None, params=None, body=None, debug=False):
    payload = _send(
        session,
        method,
        table_url(session, table, sys_id=sys_id, params=params),
        body=None if body is None else json.dumps(body).encode("utf-8"),
        content_type=None if body is None else "application/json",
        debug=debug,
    )
    if payload is None:
        return {}
    if not isinstance(payload, dict) or "result" not in payload:
        raise InternalError("SWODP response lacked a result field")
    return payload["result"]


def processor(session, name, fields, *, debug=False):
    """POST to the Service Portal time-card processor.

    State transitions are not Table API operations: the portal drives them
    through `timecardprocessor.do`, form-encoded, and answers with a bare
    `{"status": ..., "data": {...}}` object rather than a `result` envelope.
    """
    query = urlencode({"sysparm_processor": "TimeCardPortalService", "sysparm_name": name})
    payload = _send(
        session,
        "POST",
        f"https://{session.host}/timecardprocessor.do?{query}",
        body=urlencode(fields).encode("utf-8"),
        content_type="application/x-www-form-urlencoded",
        debug=debug,
    )
    if not isinstance(payload, dict):
        raise InternalError("SWODP processor response was not an object")
    return payload
