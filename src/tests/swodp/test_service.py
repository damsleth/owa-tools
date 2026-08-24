from types import SimpleNamespace

import pytest

from owa_core.errors import ScopeInsufficientError, UsageError
from owa_swodp import service

SESSION = SimpleNamespace(user="user@example.invalid")


def test_card_range_requires_monday_and_bounds():
    assert tuple(str(value) for value in service.card_range("2026-08-17", 1)) == (
        "2026-08-10",
        "2026-08-24",
    )
    with pytest.raises(UsageError, match="Monday"):
        service.card_range("2026-08-18")
    with pytest.raises(UsageError, match="between"):
        service.card_range("2026-08-17", 53)


def test_query_builders_port_fixed_shapes(monkeypatch):
    calls = []
    monkeypatch.setattr(service.api, "request", lambda *a, **k: calls.append((a, k)) or [])
    service.week_cards(SESSION, "2026-08-17")
    service.history(SESSION)
    service.allocations(SESSION, since="2026-05-01")
    service.probe(SESSION)
    assert calls[0][1]["params"]["sysparm_limit"] == "500"
    assert "week_starts_on>=2026-07-27" in calls[0][1]["params"]["sysparm_query"]
    assert calls[1][1]["params"]["sysparm_limit"] == "1000"
    assert "end_date>=2026-05-01" in calls[2][1]["params"]["sysparm_query"]
    assert calls[3][1]["params"]["sysparm_limit"] == "1"


def test_categories_maps_display_to_raw(monkeypatch):
    monkeypatch.setattr(
        service.api,
        "request",
        lambda *a, **k: [
            {"category": {"display_value": "Admin", "value": "admin"}},
            {"category": {"display_value": "Project/Project Task", "value": "project_work"}},
            {"category": "vacation"},
        ],
    )
    assert service.categories(SESSION) == {"Admin": "admin"}


def test_sync_degrades_optional_403(monkeypatch):
    monkeypatch.setattr(service, "week_cards", lambda *a, **k: [{"sys_id": "card"}])
    monkeypatch.setattr(service, "history", lambda *a, **k: [{"task.number": "TABC123"}])
    monkeypatch.setattr(
        service,
        "allocations",
        lambda *a, **k: (_ for _ in ()).throw(ScopeInsufficientError("403")),
    )
    monkeypatch.setattr(service, "categories", lambda *a, **k: {"Admin": "admin"})
    result = service.sync(SESSION, "2026-08-17")
    assert result["allocations"] == []
    assert "resource_allocation" in result["warnings"][0]
    assert result["weekCards"] == [{"sys_id": "card"}]


def valid_row(**updates):
    row = {"taskNumber": "TABC123", "days": [1, 2, 3, 4, 5, 0, 0], "description": "work"}
    row.update(updates)
    return row


def test_validate_write_rows_accepts_task_category_and_split():
    rows = [
        valid_row(),
        {"category": "admin", "days": [0] * 7, "description": "admin"},
        {"category": "admin", "days": [0] * 7, "remove": True},
        valid_row(split=True),
    ]
    assert service.validate_write_rows(rows) is rows


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [valid_row(category="admin")],
        [valid_row(taskNumber="bad")],
        [valid_row(days=[1] * 6)],
        [valid_row(days=[True] + [0] * 6)],
        [valid_row(days=[25] + [0] * 6)],
        [valid_row(split=False)],
        [valid_row(split=True, description="")],
        [valid_row(split=True, remove=True)],
        [{"category": "admin", "days": [0] * 7}],
        [valid_row(description="   ")],
    ],
)
def test_validate_write_rows_rejects_invalid(rows):
    with pytest.raises(UsageError):
        service.validate_write_rows(rows)


def test_task_lookup_validates_and_returns_first(monkeypatch):
    monkeypatch.setattr(service.api, "request", lambda *a, **k: [{"sys_id": "task-id"}])
    assert service.task_lookup(SESSION, "TABC123") == {"sys_id": "task-id"}
    with pytest.raises(UsageError):
        service.task_lookup(SESSION, "INC123")


def test_write_updates_pending_and_skips_locked(monkeypatch):
    def fake_request(session, method, table, **kwargs):
        if method == "GET" and kwargs.get("params", {}).get("sysparm_limit") == "200":
            return [
                {"sys_id": "pending", "task.number": "TABC123", "state": "Pending"},
                {"sys_id": "locked", "task.number": "TLOCK99", "state": "Approved"},
            ]
        if method == "GET" and kwargs.get("sys_id") == "pending":
            return {"comments": "saved", "notes": ""}
        return {}

    monkeypatch.setattr(service.api, "request", fake_request)
    result = service.write_week(
        SESSION,
        "2026-08-17",
        [valid_row(), valid_row(taskNumber="TLOCK99")],
    )
    assert [row["action"] for row in result] == ["updated", "skipped"]


def test_create_uses_post_without_comments_then_patch_and_verify(monkeypatch):
    calls = []

    def fake_request(session, method, table, **kwargs):
        calls.append((method, table, kwargs))
        if method == "GET" and kwargs.get("params", {}).get("sysparm_limit") == "200":
            return []
        if table == "task" and method == "GET":
            return [{"sys_id": "task-id"}]
        if table == "resource_allocation":
            raise ScopeInsufficientError("no allocation access")
        if method == "POST":
            return {"sys_id": "new-card"}
        if method == "GET" and kwargs.get("sys_id") == "new-card":
            return {"comments": "saved", "notes": ""}
        return {}

    monkeypatch.setattr(service.api, "request", fake_request)
    result = service.write_week(SESSION, "2026-08-17", [valid_row()])
    assert result[0]["action"] == "created"
    post = next(call for call in calls if call[0] == "POST")
    assert "comments" not in post[2]["body"]
    patch = next(call for call in calls if call[0] == "PATCH")
    assert patch[2]["body"] == {"comments": "work"}


def test_remove_deletes_only_pending(monkeypatch):
    calls = []

    def fake_request(session, method, table, **kwargs):
        calls.append((method, kwargs))
        if method == "GET":
            return [
                {"sys_id": "one", "category": "admin", "state": "Pending"},
                {"sys_id": "two", "category": "admin", "state": "Submitted"},
            ]
        return {}

    monkeypatch.setattr(service.api, "request", fake_request)
    result = service.write_week(
        SESSION, "2026-08-17", [{"category": "admin", "days": [0] * 7, "remove": True}]
    )
    assert [row["action"] for row in result] == ["deleted", "skipped"]
    assert [call[1]["sys_id"] for call in calls if call[0] == "DELETE"] == ["one"]


def test_split_replaces_pending_cards(monkeypatch):
    calls = []

    def fake_request(session, method, table, **kwargs):
        calls.append((method, table, kwargs))
        if method == "GET" and kwargs.get("params", {}).get("sysparm_limit") == "200":
            return [{"sys_id": "old", "task.number": "TABC123", "state": "Pending"}]
        if table == "task" and method == "GET":
            return [{"sys_id": "task-id"}]
        if table == "resource_allocation":
            return []
        if method == "POST":
            return {"sys_id": f"new-{len(calls)}"}
        if method == "GET" and kwargs.get("sys_id"):
            return {"comments": "saved"}
        return {}

    monkeypatch.setattr(service.api, "request", fake_request)
    rows = [valid_row(split=True, description="one"), valid_row(split=True, description="two")]
    result = service.write_week(SESSION, "2026-08-17", rows)
    assert [row["action"] for row in result] == ["deleted", "created", "created"]
    assert sum(call[0] == "POST" for call in calls) == 2


def test_description_verification_reports_missing_and_notes(monkeypatch):
    monkeypatch.setattr(
        service.api, "request", lambda *a, **k: {"comments": "", "notes": "fallback"}
    )
    assert "landed in notes" in service._verify_description(SESSION, "x", "sent")


def test_sync_cards_only_and_truncation(monkeypatch):
    monkeypatch.setattr(service, "week_cards", lambda *a, **k: [{}] * 500)
    result = service.sync(SESSION, "2026-08-17", cards_only=True)
    assert len(result["weekCards"]) == 500
    assert "truncated" in result["warnings"][0]
