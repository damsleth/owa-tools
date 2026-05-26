"""Direct command tests for owa-drive."""

import io
import json

import pytest

from owa_drive import cli


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})
    monkeypatch.setattr(cli.auth_mod, "setup_auth", lambda config, debug=False: ("tok", "https://graph.test"))


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


def test_main_schema_profile_and_debug(monkeypatch, capsys):
    seen = {}

    def fake_auth(config, debug=False):
        seen["config"] = dict(config)
        seen["debug"] = debug
        return "tok", "https://graph.test"

    monkeypatch.setattr(cli.auth_mod, "setup_auth", fake_auth)
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *args, **kwargs: {"value": []})

    assert cli._main(["schema"]) == 0
    assert json.loads(capsys.readouterr().out)["tool"] == "owa-drive"

    assert cli._main(["--debug", "--profile", "work", "ls", "/Documents"]) == 0
    assert seen["config"]["debug"] is True
    assert seen["config"]["owa_piggy_profile"] == "work"
    assert seen["debug"] is True


def test_ls_show_get_put_and_rm(monkeypatch, tmp_path, capfd):
    calls = []

    def fake_request(method, api_base, endpoint, access_token, **kwargs):
        calls.append((method, api_base, endpoint, access_token, kwargs))
        if method == "DELETE":
            return {}
        if endpoint.endswith("/children"):
            return {"value": [_drive_item(folder=True)]}
        return _drive_item()

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    monkeypatch.setattr(cli.api_mod, "api_get_binary", lambda *args, **kwargs: b"content")
    monkeypatch.setattr(cli.api_mod, "api_put_binary", lambda *args, **kwargs: _drive_item("uploaded.txt"))

    assert cli.cmd_ls(["/Documents"], {}, "tok", "https://graph.test") == 0
    listed = json.loads(capfd.readouterr().out)
    assert listed[0]["kind"] == "folder"
    assert calls[-1][2] == "me/drive/root:/Documents:/children"

    assert cli.cmd_show(["/Documents/report.txt", "--pretty"], {}, "tok", "https://graph.test") == 0
    assert "report.txt [file]" in capfd.readouterr().out
    assert calls[-1][2] == "me/drive/root:/Documents/report.txt:"

    out_path = tmp_path / "download.txt"
    assert cli.cmd_get(["/Documents/report.txt", "--out", str(out_path)], {}, "tok", "https://graph.test") == 0
    assert out_path.read_bytes() == b"content"
    assert "wrote 7 bytes" in capfd.readouterr().err

    assert cli.cmd_get(["/Documents/report.txt"], {}, "tok", "https://graph.test") == 0
    assert capfd.readouterr().out == "content"

    src = tmp_path / "upload.txt"
    src.write_bytes(b"upload")
    assert cli.cmd_put([str(src), "/Documents/upload.txt"], {}, "tok", "https://graph.test") == 0
    assert json.loads(capfd.readouterr().out)["name"] == "uploaded.txt"

    monkeypatch.setattr(cli.sys, "stdin", type("Stdin", (), {"buffer": io.BytesIO(b"stdin-data")})())
    assert cli.cmd_put(["-", "/Documents/stdin.txt"], {}, "tok", "https://graph.test") == 0
    assert json.loads(capfd.readouterr().out)["id"] == "item-1"

    assert cli.cmd_rm(["/Documents/report.txt", "--confirm"], {}, "tok", "https://graph.test") == 0
    assert calls[-1][0] == "DELETE"
    assert "deleted: /Documents/report.txt" in capfd.readouterr().err


def test_put_large_file_uses_upload_session(monkeypatch, tmp_path, capfd):
    seen = {}

    def fake_session(api_base, endpoint, token, data, **kwargs):
        seen['endpoint'] = endpoint
        seen['size'] = len(data)
        return _drive_item("big.bin")

    monkeypatch.setattr(cli.api_mod, "api_upload_session", fake_session)
    monkeypatch.setattr(
        cli.api_mod, "api_put_binary",
        lambda *a, **k: pytest.fail("small path used for large file"),
    )

    src = tmp_path / "big.bin"
    src.write_bytes(b"x" * (cli.api_mod.UPLOAD_LIMIT_BYTES + 1))
    assert cli.cmd_put([str(src), "/Documents/big.bin"], {}, "tok", "https://graph.test") == 0
    out = capfd.readouterr()
    assert json.loads(out.out)["name"] == "big.bin"
    assert "upload session" in out.err
    assert seen['endpoint'] == "me/drive/root:/Documents/big.bin:/createUploadSession"
    assert seen['size'] == cli.api_mod.UPLOAD_LIMIT_BYTES + 1


def test_put_large_file_to_root_rejected(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        cli.api_mod, "api_upload_session",
        lambda *a, **k: pytest.fail("session created for root path"),
    )
    src = tmp_path / "big.bin"
    src.write_bytes(b"x" * (cli.api_mod.UPLOAD_LIMIT_BYTES + 1))
    assert cli.cmd_put([str(src), "/"], {}, "tok", "https://graph.test") == 1
    assert "root has no content" in capsys.readouterr().err


def test_put_large_file_session_failure_returns_one(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.api_mod, "api_upload_session", lambda *a, **k: None)
    src = tmp_path / "big.bin"
    src.write_bytes(b"x" * (cli.api_mod.UPLOAD_LIMIT_BYTES + 1))
    assert cli.cmd_put([str(src), "/Documents/big.bin"], {}, "tok", "https://graph.test") == 1


def test_drive_validation_confirm_and_failures(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.api_mod, "api_get_binary", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.api_mod, "api_put_binary", lambda *args, **kwargs: None)

    assert cli.cmd_ls([], {}, "tok", "https://graph.test") == 1
    assert cli.cmd_show([], {}, "tok", "https://graph.test") == 1
    assert "show requires" in capsys.readouterr().err
    assert cli.cmd_get([], {}, "tok", "https://graph.test") == 1
    assert "get requires" in capsys.readouterr().err
    assert cli.cmd_get(["/"], {}, "tok", "https://graph.test") == 1
    assert "root has no content" in capsys.readouterr().err
    assert cli.cmd_put([], {}, "tok", "https://graph.test") == 1
    assert "put requires" in capsys.readouterr().err
    assert cli.cmd_put([str(tmp_path / "missing"), "/x"], {}, "tok", "https://graph.test") == 1
    assert "cannot read" in capsys.readouterr().err
    monkeypatch.setattr(cli.sys, "stdin", type("Stdin", (), {"buffer": io.BytesIO(b"stdin-data")})())
    assert cli.cmd_put(["-", "/"], {}, "tok", "https://graph.test") == 1
    assert "root has no content" in capsys.readouterr().err
    assert cli.cmd_rm([], {}, "tok", "https://graph.test") == 1
    assert "rm requires" in capsys.readouterr().err
    assert cli.cmd_rm(["/", "--confirm"], {}, "tok", "https://graph.test") == 1
    assert "refuse to delete" in capsys.readouterr().err

    monkeypatch.setattr(cli.api_mod, "api_request", lambda *args, **kwargs: {})
    monkeypatch.setattr(cli.tty_mod, "require_confirm_or_tty", lambda action: None)
    monkeypatch.setattr(cli.tty_mod, "confirm", lambda prompt, accepted: False)
    assert cli.cmd_rm(["/x"], {}, "tok", "https://graph.test") == 1
    assert "aborted" in capsys.readouterr().err

    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_ls(["--bad"], {}, "tok", "https://graph.test")


def test_drive_config_and_refresh(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, "CONFIG_PATH", "/tmp/owa-drive-config")
    monkeypatch.setattr(cli.config_mod, "config_set", lambda key, value: saved.setdefault(key, value))

    assert cli.cmd_config([], {"owa_piggy_profile": "work"}) == 0
    assert "owa_piggy_profile=work" in capsys.readouterr().err
    assert cli.cmd_config(["--profile", "home"], {}) == 0
    assert saved["owa_piggy_profile"] == "home"

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *args, **kwargs: {"displayName": "Ada"})
    assert cli.cmd_refresh([], {}) == 0
    assert "Authenticated as Ada" in capsys.readouterr().err

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "")
    assert cli.cmd_refresh([], {}) == 1
    assert "Token refresh failed" in capsys.readouterr().err

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *args, **kwargs: None)
    assert cli.cmd_refresh([], {}) == 1
    assert "Auth verification failed" in capsys.readouterr().err
