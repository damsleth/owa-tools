"""Argument validation and id-parsing for owa-todo.

Covers the positional-OR-`--id` acceptance and the `--limit` clamp added
in the suite CLI-uniformity pass. No network, no real tokens.
"""
import pytest

from owa_todo import cli


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {"default_timezone": "UTC"})
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth",
        lambda config, debug=False: ("tok", "https://outlook.test"),
    )


def _capture_request(monkeypatch):
    seen = {}

    def fake_request(method, base, path, token, **kw):
        seen["method"] = method
        seen["path"] = path
        return {"Id": "t1", "Subject": "x", "Status": "Completed"}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    return seen


def test_done_accepts_positional_id(monkeypatch):
    seen = _capture_request(monkeypatch)
    assert cli.cmd_done(["AAMkTASK123"], {}, "tok", "https://outlook.test") == 0
    assert "AAMkTASK123" in seen["path"]


def test_done_accepts_flag_id(monkeypatch):
    seen = _capture_request(monkeypatch)
    assert cli.cmd_done(["--id", "AAMkTASK123"], {}, "tok", "https://outlook.test") == 0
    assert "AAMkTASK123" in seen["path"]


def test_delete_accepts_positional_id(monkeypatch):
    seen = _capture_request(monkeypatch)
    assert cli.cmd_delete(["AAMkTASK123", "--confirm"], {}, "tok", "https://outlook.test") == 0
    assert seen["method"] == "DELETE"
    assert "AAMkTASK123" in seen["path"]


def test_update_accepts_positional_id(monkeypatch):
    seen = _capture_request(monkeypatch)
    rc = cli.cmd_update(
        ["AAMkTASK123", "--status", "completed"], {"default_timezone": "UTC"},
        "tok", "https://outlook.test",
    )
    assert rc == 0
    assert "AAMkTASK123" in seen["path"]


def test_explicit_flag_overrides_positional(monkeypatch):
    seen = _capture_request(monkeypatch)
    cli.cmd_done(["POSID", "--id", "FLAGID"], {}, "tok", "https://outlook.test")
    assert "FLAGID" in seen["path"]


def test_tasks_limit_is_clamped_to_200(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        cli, "_fetch_tasks",
        lambda endpoint, all_pages, tok, base, debug: seen.update(endpoint=endpoint) or {"value": []},
    )
    cli.cmd_tasks(["--limit", "9999"], {}, "tok", "https://outlook.test")
    assert "top=200" in seen["endpoint"]
    assert "9999" not in seen["endpoint"]


def test_tasks_limit_floor_is_one(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        cli, "_fetch_tasks",
        lambda endpoint, all_pages, tok, base, debug: seen.update(endpoint=endpoint) or {"value": []},
    )
    cli.cmd_tasks(["--limit", "0"], {}, "tok", "https://outlook.test")
    assert "top=1" in seen["endpoint"]
