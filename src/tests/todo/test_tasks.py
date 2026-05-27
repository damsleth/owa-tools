"""Pure-function tests for owa_todo.tasks (normalizers + builders)."""

from owa_todo import tasks


def test_normalize_status_and_importance():
    assert tasks.normalize_status("done") == "Completed"
    assert tasks.normalize_status("in-progress") == "InProgress"
    assert tasks.normalize_status("Completed") == "Completed"  # already wire form
    assert tasks.normalize_status("bogus") is None
    assert tasks.normalize_status("") is None
    assert tasks.normalize_importance("high") == "High"
    assert tasks.normalize_importance("") is None


def test_to_local_treats_naive_as_utc():
    # conftest pins TZ=UTC, so UTC in -> UTC out (no date drift).
    assert tasks.to_local("2026-06-01T00:00:00Z") == "2026-06-01T00:00:00"
    assert tasks.to_local("2026-06-01T00:00:00.1234567") == "2026-06-01T00:00:00"
    assert tasks.to_local("") == ""
    assert tasks.to_local("not-a-date") == "not-a-date"


def test_normalize_folder():
    folder = tasks.normalize_folder({"Id": "f1", "Name": "Tasks", "IsDefaultFolder": True})
    assert folder == {"id": "f1", "name": "Tasks", "default": True}


def test_normalize_task_flattens_fields():
    raw = {
        "Id": "t1", "Subject": "Buy milk", "Status": "NotStarted",
        "Importance": "High",
        "DueDateTime": {"DateTime": "2026-06-01T00:00:00", "TimeZone": "UTC"},
        "CompletedDateTime": None, "ParentFolderId": "f1",
        "Categories": ["shopping"], "IsReminderOn": False,
        "ReminderDateTime": {"DateTime": "2026-05-31T09:00:00", "TimeZone": "UTC"},
    }
    t = tasks.normalize_task(raw)
    assert t["id"] == "t1"
    assert t["subject"] == "Buy milk"
    assert t["due"] == "2026-06-01"
    assert t["completed"] == ""
    assert t["reminder"] == ""  # IsReminderOn False -> suppressed
    assert t["categories"] == ["shopping"]
    assert t["folderId"] == "f1"


def test_normalize_task_reminder_when_on():
    t = tasks.normalize_task({
        "Id": "t2", "Subject": "x", "IsReminderOn": True,
        "ReminderDateTime": {"DateTime": "2026-05-31T09:00:00", "TimeZone": "UTC"},
    })
    assert t["reminder"] == "2026-05-31T09:00:00"


def test_build_task_json():
    body = tasks.build_task_json(
        "Buy milk", importance="high", due="2026-06-01", body_text="2%", tz="UTC",
    )
    assert body["Subject"] == "Buy milk"
    assert body["Importance"] == "High"
    assert body["DueDateTime"] == {"DateTime": "2026-06-01T00:00:00", "TimeZone": "UTC"}
    assert body["Body"] == {"ContentType": "Text", "Content": "2%"}
    # Minimal create defaults Importance to Normal and sets no dates.
    assert tasks.build_task_json("x") == {"Subject": "x", "Importance": "Normal"}


def test_build_task_patch_only_provided_keys():
    patch = tasks.build_task_patch(
        {"subject": "y", "status": "done", "importance": "low", "due": "2026-06-02"}, "UTC",
    )
    assert patch["Subject"] == "y"
    assert patch["Status"] == "Completed"
    assert patch["Importance"] == "Low"
    assert patch["DueDateTime"]["DateTime"].startswith("2026-06-02")
    assert "StartDateTime" not in patch
    assert tasks.build_task_patch({}, "UTC") == {}
