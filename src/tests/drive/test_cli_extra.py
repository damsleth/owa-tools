"""Extra coverage tests for owa_drive.cli and owa_drive.api.

Covers cli.py missing lines:
- _require_value raises on empty args
- print_help() output
- cmd_ls: unknown flag, extra positional argument, --all+pretty, --all+json
- cmd_show: no path, unknown flag, extra positional arg
- cmd_get: --out flag, unknown flag, extra positional arg, ValueError from content_endpoint
- cmd_put: <2 positional args, batch-mode stdin rejection, _upload_one OSError path
- cmd_rm: no path, unknown flag, extra positional arg, ValueError from delete_endpoint
- cmd_config: unknown flag, no profile set path
- cmd_refresh: extra arg, no displayName, api returns non-dict
- _main dispatch: no args, help/--help/-h, --version/-v, --debug flag,
                  empty after filter, config, refresh, unknown command,
                  all canonical aliases (list/download/upload/delete)

Covers api.py missing lines:
- _handle_owa_error: generic OwaError branch (emit + None), non-OwaError re-raise
- paginate_all: OwaError maps to None
- api_get_binary: OwaError maps to None
- api_put_binary: debug print path
- api_put_binary: OwaError maps to None
- api_upload_session: non-dict session (emit + None), debug print on success
"""

import json

import pytest

from owa_core.errors import (
    AuthExpiredError,
    NetworkError,
    NotFoundError,
    OwaError,
)
from owa_core.http import Response
from owa_drive import api as api_mod
from owa_drive import cli

# ---------------------------------------------------------------------------
# Autouse fixture: stub config + auth + remote-exists (assume not present)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth",
        lambda config, debug=False: ("tok", "https://graph.test"),
    )
    monkeypatch.setattr(cli, "_remote_exists", lambda *a, **kw: False)


def _drive_item(name="report.txt", *, folder=False):
    item = {
        "id": "item-1",
        "name": name,
        "size": 12,
        "lastModifiedDateTime": "2026-05-09T12:00:00Z",
        "webUrl": "https://example.test/item",
        "parentReference": {"path": "/drive/root:/Documents"},
    }
    if folder:
        item["folder"] = {"childCount": 3}
    else:
        item["file"] = {"mimeType": "text/plain"}
    return item


# ===========================================================================
# cli._require_value
# ===========================================================================

def test_require_value_raises_when_args_empty():
    with pytest.raises(cli.UsageError, match="requires a value"):
        cli._require_value("--out", [])


# ===========================================================================
# print_help
# ===========================================================================

def test_print_help_contains_usage(capsys):
    cli.print_help()
    out = capsys.readouterr().out
    assert "Usage: owa-drive" in out
    assert "ls" in out
    assert "get" in out
    assert "put" in out
    assert "rm" in out


# ===========================================================================
# cmd_ls
# ===========================================================================

def test_ls_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_ls(["--bogus"], {}, "tok", "https://graph.test")


def test_ls_extra_positional_raises():
    with pytest.raises(cli.UsageError, match="Unexpected argument"):
        cli.cmd_ls(["/Docs", "/Extra"], {}, "tok", "https://graph.test")


def test_ls_all_pages_json(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "paginate_all",
        lambda base, endpoint, token, debug=False: [_drive_item()],
    )
    rc = cli.cmd_ls(["--all"], {}, "tok", "https://graph.test")
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list)
    assert data[0]["name"] == "report.txt"


def test_ls_all_pages_pretty(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "paginate_all",
        lambda base, endpoint, token, debug=False: [_drive_item()],
    )
    rc = cli.cmd_ls(["--all", "--pretty"], {}, "tok", "https://graph.test")
    assert rc == 0
    assert capsys.readouterr().out != ""


def test_ls_all_pages_returns_none(monkeypatch):
    monkeypatch.setattr(
        cli.api_mod, "paginate_all",
        lambda base, endpoint, token, debug=False: None,
    )
    assert cli.cmd_ls(["--all"], {}, "tok", "https://graph.test") == 1


# ===========================================================================
# cmd_show
# ===========================================================================

def test_show_missing_path_raises():
    with pytest.raises(cli.UsageError, match="show requires a path"):
        cli.cmd_show([], {}, "tok", "https://graph.test")


def test_show_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_show(["--nope"], {}, "tok", "https://graph.test")


def test_show_extra_positional_raises():
    with pytest.raises(cli.UsageError, match="Unexpected argument"):
        cli.cmd_show(["/a.txt", "/b.txt"], {}, "tok", "https://graph.test")


def test_show_json_output(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "api_request",
        lambda *a, **kw: _drive_item(),
    )
    rc = cli.cmd_show(["/Documents/report.txt"], {}, "tok", "https://graph.test")
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["name"] == "report.txt"


def test_show_pretty_output(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "api_request",
        lambda *a, **kw: _drive_item(),
    )
    rc = cli.cmd_show(["/Documents/report.txt", "--pretty"], {}, "tok", "https://graph.test")
    assert rc == 0
    assert capsys.readouterr().out != ""


def test_show_api_none_returns_1(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **kw: None)
    assert cli.cmd_show(["/Documents/report.txt"], {}, "tok", "https://graph.test") == 1


# ===========================================================================
# cmd_get
# ===========================================================================

def test_get_missing_path_raises():
    with pytest.raises(cli.UsageError, match="get requires a path"):
        cli.cmd_get([], {}, "tok", "https://graph.test")


def test_get_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_get(["--bogus"], {}, "tok", "https://graph.test")


def test_get_extra_positional_raises():
    with pytest.raises(cli.UsageError, match="Unexpected argument"):
        cli.cmd_get(["/a.txt", "/b.txt"], {}, "tok", "https://graph.test")


def test_get_out_flag_writes_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        cli.api_mod, "api_get_binary",
        lambda base, endpoint, token, debug=False: b"hello!",
    )
    out_file = tmp_path / "out.txt"
    rc = cli.cmd_get(["/a.txt", "--out", str(out_file)], {}, "tok", "https://graph.test")
    assert rc == 0
    assert out_file.read_bytes() == b"hello!"
    assert "6 bytes" in capsys.readouterr().err


def test_get_api_none_returns_1(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get_binary", lambda *a, **kw: None)
    assert cli.cmd_get(["/a.txt"], {}, "tok", "https://graph.test") == 1


def test_get_invalid_path_returns_1(monkeypatch, capsys):
    """cmd_get catches ValueError from content_endpoint (e.g. root path)."""
    monkeypatch.setattr(
        cli.paths_mod, "content_endpoint",
        lambda path: (_ for _ in ()).throw(ValueError("cannot resolve")),
    )
    rc = cli.cmd_get(["/"], {}, "tok", "https://graph.test")
    assert rc == 1


# ===========================================================================
# cmd_put
# ===========================================================================

def test_put_missing_args_raises():
    with pytest.raises(cli.UsageError, match="put requires"):
        cli.cmd_put([], {}, "tok", "https://graph.test")


def test_put_only_one_positional_raises():
    with pytest.raises(cli.UsageError, match="put requires"):
        cli.cmd_put(["/local.txt"], {}, "tok", "https://graph.test")


def test_put_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_put(["--nope", "/a.txt", "/b.txt"], {}, "tok", "https://graph.test")


def test_put_batch_stdin_rejected():
    """Batch mode must reject '-' as local source."""
    with pytest.raises(cli.UsageError, match="batch put cannot read from stdin"):
        cli.cmd_put(["-", "/b.txt", "/Docs"], {}, "tok", "https://graph.test")


def test_put_single_upload_error_returns_1(monkeypatch, tmp_path):
    src = tmp_path / "f.txt"
    src.write_bytes(b"data")
    monkeypatch.setattr(cli.api_mod, "api_put_binary", lambda *a, **kw: None)
    rc = cli.cmd_put([str(src), "/Docs/f.txt"], {}, "tok", "https://graph.test")
    assert rc == 1


def test_put_upload_one_oserror_returns_failed(monkeypatch, tmp_path, capsys):
    """_upload_one surfaces an OSError as ('failed', None)."""
    result = cli._upload_one(
        "/nonexistent-path-xyz.txt", "/Docs/x.txt",
        config={}, access_token="tok", api_base="https://graph.test", debug=False,
    )
    assert result[0] == "failed"
    assert "cannot read" in capsys.readouterr().err


def test_resolve_batch_remote_empty_basename_raises():
    with pytest.raises(cli.UsageError, match="cannot derive remote name"):
        cli._resolve_batch_remote("/Docs/", "/")


# ===========================================================================
# cmd_rm
# ===========================================================================

def test_rm_missing_path_raises():
    with pytest.raises(cli.UsageError, match="rm requires a path"):
        cli.cmd_rm([], {}, "tok", "https://graph.test")


def test_rm_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_rm(["--bogus"], {}, "tok", "https://graph.test")


def test_rm_extra_positional_raises():
    with pytest.raises(cli.UsageError, match="Unexpected argument"):
        cli.cmd_rm(["/a.txt", "/b.txt"], {}, "tok", "https://graph.test")


def test_rm_api_none_returns_1(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **kw: None)
    rc = cli.cmd_rm(["/Documents/old.txt", "--confirm"], {}, "tok", "https://graph.test")
    assert rc == 1


def test_rm_succeeds_with_confirm(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **kw: {})
    rc = cli.cmd_rm(["/Documents/old.txt", "--confirm"], {}, "tok", "https://graph.test")
    assert rc == 0
    assert "deleted:" in capsys.readouterr().err


def test_rm_invalid_endpoint_returns_1(monkeypatch, capsys):
    """cmd_rm catches ValueError from delete_endpoint (e.g. root path)."""
    monkeypatch.setattr(
        cli.paths_mod, "delete_endpoint",
        lambda path: (_ for _ in ()).throw(ValueError("cannot delete root")),
    )
    rc = cli.cmd_rm(["/", "--confirm"], {}, "tok", "https://graph.test")
    assert rc == 1


# ===========================================================================
# cmd_config
# ===========================================================================

def test_drive_config_unknown_flag_raises():
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_config(["--bogus"], {})


def test_drive_config_no_profile_shows_not_set(capsys):
    rc = cli.cmd_config([], {})
    assert rc == 0
    assert "not set" in capsys.readouterr().err


# ===========================================================================
# cmd_refresh
# ===========================================================================

def test_drive_refresh_extra_arg_raises():
    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_refresh(["--extra"], {})


def test_drive_refresh_token_fail_returns_1(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "")
    rc = cli.cmd_refresh([], {})
    assert rc == 1
    assert "Token refresh failed" in capsys.readouterr().err


def test_drive_refresh_api_non_dict_returns_1(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **kw: None)
    rc = cli.cmd_refresh([], {})
    assert rc == 1
    assert "Auth verification failed" in capsys.readouterr().err


def test_drive_refresh_no_displayname_still_succeeds(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **kw: {"id": "abc"})
    rc = cli.cmd_refresh([], {})
    assert rc == 0
    assert "Authenticated as" not in capsys.readouterr().err


# ===========================================================================
# _main dispatch
# ===========================================================================

def test_main_no_args_shows_help(capsys):
    assert cli._main([]) == 0
    assert "Usage: owa-drive" in capsys.readouterr().out


def test_main_help_flag(capsys):
    assert cli._main(["help"]) == 0
    assert "Usage: owa-drive" in capsys.readouterr().out


def test_main_double_help_flag(capsys):
    assert cli._main(["--help"]) == 0
    assert "Usage: owa-drive" in capsys.readouterr().out


def test_main_h_flag(capsys):
    assert cli._main(["-h"]) == 0
    assert "Usage: owa-drive" in capsys.readouterr().out


def test_main_version_flag(capsys):
    assert cli._main(["--version"]) == 0
    assert "owa-drive" in capsys.readouterr().out


def test_main_v_flag(capsys):
    assert cli._main(["-v"]) == 0
    assert "owa-drive" in capsys.readouterr().out


def test_main_debug_flag_sets_config(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "api_request",
        lambda *a, **kw: {"value": []},
    )
    rc = cli._main(["--debug", "ls"])
    assert rc == 0
    assert "verbose logging" in capsys.readouterr().err


def test_main_empty_after_filter_shows_help(capsys):
    # --debug alone strips to empty argv
    assert cli._main(["--debug"]) == 0
    assert "Usage: owa-drive" in capsys.readouterr().out


def test_main_profile_override(monkeypatch, capsys):
    seen = {}

    def fake_auth(config, debug=False):
        seen["profile"] = config.get("owa_piggy_profile")
        return "tok", "https://graph.test"

    monkeypatch.setattr(cli.auth_mod, "setup_auth", fake_auth)
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **kw: {"value": []})
    cli._main(["--profile", "myprofile", "ls"])
    assert seen["profile"] == "myprofile"


def test_main_config_dispatch(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, "config_set", lambda k, v: saved.setdefault(k, v))
    rc = cli._main(["config", "--profile", "home"])
    assert rc == 0
    assert saved["owa_piggy_profile"] == "home"


def test_main_refresh_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **kw: {"displayName": "Ada"})
    rc = cli._main(["refresh"])
    assert rc == 0
    assert "Authenticated as Ada" in capsys.readouterr().err


def test_main_unknown_command_raises():
    with pytest.raises(cli.UsageError, match="Unknown command"):
        cli._main(["frobnicate"])


def test_main_alias_list_resolves_to_ls(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **kw: {"value": []})
    assert cli._main(["list"]) == 0


def test_main_alias_download_resolves_to_get(monkeypatch, capfd):
    monkeypatch.setattr(
        cli.api_mod, "api_get_binary",
        lambda *a, **kw: b"data",
    )
    rc = cli._main(["download", "/file.txt"])
    assert rc == 0


def test_main_alias_upload_resolves_to_put(monkeypatch, tmp_path, capsys):
    src = tmp_path / "f.txt"
    src.write_bytes(b"data")
    monkeypatch.setattr(
        cli.api_mod, "api_put_binary",
        lambda *a, **kw: _drive_item("f.txt"),
    )
    rc = cli._main(["upload", str(src), "/Docs/f.txt"])
    assert rc == 0


def test_main_alias_delete_resolves_to_rm(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **kw: {})
    rc = cli._main(["delete", "/old.txt", "--confirm"])
    assert rc == 0


def test_main_profile_requires_value_raises():
    with pytest.raises(cli.UsageError, match="--profile requires a value"):
        cli._main(["--profile"])


# ===========================================================================
# api.py — uncovered branches
# ===========================================================================

def test_handle_owa_error_generic_owa_subclass_raises():
    """A bare OwaError subclass propagates to the CLI mode wrapper."""

    class CustomOwaError(OwaError):
        pass

    # The function is internal; call through api_request which delegates to it.
    def fake_request(method, url, **kwargs):
        raise CustomOwaError("something went wrong")

    import owa_drive.api as api
    original = api.http.request
    api.http.request = fake_request
    try:
        with pytest.raises(CustomOwaError):
            api.api_request("GET", "https://graph.test", "/x", "tok")
    finally:
        api.http.request = original


def test_handle_owa_error_non_owa_exception_is_reraised():
    """A non-OwaError propagates unchanged (the final raise branch)."""
    import owa_drive.api as api

    def fake_request(method, url, **kwargs):
        raise ValueError("unexpected")

    original = api.http.request
    api.http.request = fake_request
    try:
        with pytest.raises(ValueError, match="unexpected"):
            api.api_request("GET", "https://graph.test", "/x", "tok")
    finally:
        api.http.request = original


def test_paginate_all_owa_error_raises(monkeypatch):
    monkeypatch.setattr(
        api_mod.http, "paginate",
        lambda url, token, headers, debug: (_ for _ in ()).throw(NetworkError("net fail")),
    )
    with pytest.raises(NetworkError):
        api_mod.paginate_all("https://graph.test", "/me/drive/root/children", "tok")


def test_api_get_binary_owa_error_raises(monkeypatch):
    monkeypatch.setattr(
        api_mod.http, "request",
        lambda method, url, **kw: (_ for _ in ()).throw(NotFoundError("not found")),
    )
    with pytest.raises(NotFoundError):
        api_mod.api_get_binary("https://graph.test", "/content", "tok")


def test_api_put_binary_debug_prints_to_stderr(monkeypatch, capsys):
    monkeypatch.setattr(
        api_mod.http, "request",
        lambda method, url, **kw: Response(status=200, headers={}, json={"id": "1"}, bytes=b"{}"),
    )
    api_mod.api_put_binary("https://graph.test", "/content", "tok", b"abc", debug=True)
    assert "DEBUG: PUT" in capsys.readouterr().err


def test_api_put_binary_owa_error_raises(monkeypatch):
    monkeypatch.setattr(
        api_mod.http, "request",
        lambda method, url, **kw: (_ for _ in ()).throw(NetworkError("net error")),
    )
    with pytest.raises(NetworkError):
        api_mod.api_put_binary("https://graph.test", "/content", "tok", b"abc")


def test_api_upload_session_non_dict_response_returns_none(monkeypatch, capsys):
    """If the POST body is not a dict (e.g. None), emit + return None."""
    monkeypatch.setattr(
        api_mod.http, "request",
        lambda method, url, **kw: Response(status=200, headers={}, json=None, bytes=b"null"),
    )
    result = api_mod.api_upload_session(
        "https://graph.test",
        "me/drive/root:/big.bin:/createUploadSession",
        "tok",
        b"x" * 100,
    )
    assert result is None
    assert "upload session creation returned no body" in capsys.readouterr().err


def test_api_upload_session_debug_logs_created_session(monkeypatch, capsys):
    monkeypatch.setattr(
        api_mod.http, "request",
        lambda method, url, **kw: Response(
            status=200, headers={},
            json={"uploadUrl": "https://up.example.test/sess"},
            bytes=b"{}",
        ),
    )
    monkeypatch.setattr(
        api_mod.upload_mod, "upload_session",
        lambda upload_url, content, **kw: {"id": "1"},
    )
    result = api_mod.api_upload_session(
        "https://graph.test",
        "me/drive/root:/big.bin:/createUploadSession",
        "tok",
        b"x" * 100,
        debug=True,
    )
    assert result == {"id": "1"}
    assert "created upload session" in capsys.readouterr().err


def test_api_upload_session_auth_error_reraises(monkeypatch):
    monkeypatch.setattr(
        api_mod.http, "request",
        lambda method, url, **kw: (_ for _ in ()).throw(AuthExpiredError("auth expired")),
    )
    with pytest.raises(AuthExpiredError):
        api_mod.api_upload_session(
            "https://graph.test",
            "me/drive/root:/big.bin:/createUploadSession",
            "tok",
            b"x",
        )
