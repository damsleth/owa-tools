"""Tests for owa_todo.format pretty rendering."""

from owa_todo.format import format_folders_pretty, format_tasks_pretty


def test_format_tasks_pretty():
    assert format_tasks_pretty([]) == "No tasks found."
    rows = [
        {"subject": "Buy milk", "status": "NotStarted", "importance": "High",
         "due": "2026-06-01", "categories": []},
        {"subject": "Email Ada", "status": "Completed", "importance": "Normal",
         "due": "", "categories": ["work"]},
    ]
    out = format_tasks_pretty(rows)
    assert "[ ]" in out  # open task
    assert "[x]" in out  # completed task
    assert "Buy milk" in out and "due 2026-06-01" in out
    assert "[work]" in out


def test_format_folders_pretty():
    assert format_folders_pretty([]) == "No task folders found."
    out = format_folders_pretty([
        {"name": "Tasks", "default": True},
        {"name": "Work", "default": False},
    ])
    assert "* Tasks" in out
    assert "  Work" in out
