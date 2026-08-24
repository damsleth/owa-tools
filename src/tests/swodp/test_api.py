import json
from types import SimpleNamespace

import pytest

from owa_core.errors import AuthExpiredError, InternalError
from owa_core.http import Response
from owa_swodp import api

SESSION = SimpleNamespace(
    host="swodp.example.invalid",
    instance="prod",
    user_token="fake-user-token",
    cookie_header="fake-cookie=fake-value",
)


def response(payload, *, headers=None):
    raw = json.dumps(payload).encode()
    return Response(200, headers or {"Content-Type": "application/json"}, None, raw)


def test_table_url_encodes_query():
    url = api.table_url(SESSION, "time_card", sys_id="abc", params={"sysparm_limit": "1"})
    assert url == "https://swodp.example.invalid/api/now/table/time_card/abc?sysparm_limit=1"


def test_request_adds_session_headers_and_decodes(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen.update(method=method, url=url, **kwargs)
        return response({"result": [{"sys_id": "x"}]})

    monkeypatch.setattr(api.http, "request_unauthenticated", fake_request)
    assert api.request(SESSION, "POST", "time_card", body={"monday": "1"}) == [{"sys_id": "x"}]
    assert seen["headers"]["X-UserToken"] == "fake-user-token"
    assert json.loads(seen["body"]) == {"monday": "1"}


def test_request_maps_html_and_401_to_swodp_setup(monkeypatch):
    monkeypatch.setattr(
        api.http,
        "request_unauthenticated",
        lambda *a, **k: Response(200, {"Content-Type": "text/html"}, None, b"<html>login"),
    )
    with pytest.raises(AuthExpiredError, match="redirected"):
        api.request(SESSION, "GET", "time_card")

    def expired(*args, **kwargs):
        raise AuthExpiredError("auth expired")

    monkeypatch.setattr(api.http, "request_unauthenticated", expired)
    with pytest.raises(AuthExpiredError) as caught:
        api.request(SESSION, "GET", "time_card")
    assert "owa-swodp setup" in caught.value.remediation


@pytest.mark.parametrize("payload", [b"not-json", b"{}"])
def test_request_rejects_invalid_payload(monkeypatch, payload):
    monkeypatch.setattr(
        api.http,
        "request_unauthenticated",
        lambda *a, **k: Response(200, {}, None, payload),
    )
    with pytest.raises(InternalError):
        api.request(SESSION, "GET", "time_card")


def test_empty_delete_response(monkeypatch):
    monkeypatch.setattr(
        api.http,
        "request_unauthenticated",
        lambda *a, **k: Response(204, {}, None, b""),
    )
    assert api.request(SESSION, "DELETE", "time_card") == {}


def test_processor_posts_form_encoded_and_returns_bare_object(monkeypatch):
    seen = {}

    def fake(method, url, *, body=None, headers=None, debug=False):
        seen.update(method=method, url=url, body=body, headers=headers)
        return SimpleNamespace(
            bytes=b'{"status": "success", "data": {"message": "done"}}',
            headers={"Content-Type": "application/json"},
        )

    monkeypatch.setattr(api.http, "request_unauthenticated", fake)
    payload = api.processor(SESSION, "updateTimeCardState", {"timecard_id": "x", "new_state": "Submitted"})
    assert payload == {"status": "success", "data": {"message": "done"}}
    assert seen["method"] == "POST"
    assert "timecardprocessor.do" in seen["url"]
    assert "sysparm_name=updateTimeCardState" in seen["url"]
    assert seen["body"] == b"timecard_id=x&new_state=Submitted"
    assert seen["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert seen["headers"]["X-UserToken"] == SESSION.user_token


def test_processor_rejects_non_object(monkeypatch):
    monkeypatch.setattr(
        api.http,
        "request_unauthenticated",
        lambda *a, **k: SimpleNamespace(bytes=b"[]", headers={"Content-Type": "application/json"}),
    )
    with pytest.raises(InternalError):
        api.processor(SESSION, "updateTimeCardState", {})
