"""RequestContext tests."""

import json

from owa_graph.ctx import RequestContext


def _ctx(**kwargs):
    return RequestContext({}, "tok", "https://graph.test/v1.0", **kwargs)


def test_get_merges_headers_and_emits_json(monkeypatch, capsys):
    seen = {}

    def fake_request(method, base, url, token, **kwargs):
        seen.update(method=method, base=base, url=url, token=token, kwargs=kwargs)
        return {"value": [{"id": "1"}]}

    from owa_graph import ctx as ctx_mod

    monkeypatch.setattr(ctx_mod.api_mod, "api_request", fake_request)
    rc = _ctx(extra_headers={"Prefer": "x"}).get("/me", headers={"ConsistencyLevel": "eventual"})

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == {"value": [{"id": "1"}]}
    assert seen["method"] == "GET"
    assert seen["kwargs"]["extra_headers"] == {"Prefer": "x", "ConsistencyLevel": "eventual"}


def test_mutating_delete_pretty_and_ndjson(monkeypatch, capsys):
    from owa_graph import ctx as ctx_mod

    monkeypatch.setattr(ctx_mod.api_mod, "api_request", lambda *args, **kwargs: {"id": "1"})
    assert _ctx(pretty=True).post("/me/sendMail", {"x": 1}) == 0
    assert '"id": "1"' in capsys.readouterr().out

    assert _ctx(ndjson=True).patch("/me", {"x": 1}) == 0
    assert capsys.readouterr().out.strip() == '{"id": "1"}'

    assert _ctx().put("/me/photo", b"bytes", headers={"Content-Type": "image/png"}) == 0
    assert json.loads(capsys.readouterr().out) == {"id": "1"}

    monkeypatch.setattr(ctx_mod.api_mod, "api_request", lambda *args, **kwargs: {})
    assert _ctx().delete("/me/messages/m1") == 0
    assert capsys.readouterr().out == ""

    monkeypatch.setattr(ctx_mod.api_mod, "api_request", lambda *args, **kwargs: None)
    assert _ctx().delete("/me/messages/m1") == 1
    assert _ctx().post("/me/sendMail", {}) == 1


def test_paginated_output(monkeypatch, capsys):
    from owa_graph import ctx as ctx_mod

    monkeypatch.setattr(ctx_mod.api_mod, "paginate", lambda *args, **kwargs: iter([{"id": "1"}, {"id": "2"}]))

    assert _ctx(ndjson=True).get("/users", paginate=True) == 0
    assert capsys.readouterr().out.splitlines() == ['{"id": "1"}', '{"id": "2"}']

    assert _ctx().get("/users", paginate=True) == 0
    assert json.loads(capsys.readouterr().out) == {"value": [{"id": "1"}, {"id": "2"}]}

    assert _ctx(pretty=True).get("/users", paginate=True) == 0
    assert '"value"' in capsys.readouterr().out
