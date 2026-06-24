"""Direct command tests for owa-drive."""

import io
import json

import pytest

from owa_drive import cli


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})
    monkeypatch.setattr(cli.auth_mod, "setup_auth", lambda config, debug=False: ("tok", "https://graph.test"))
    # Default the put preflight to "remote does not exist" so existing
    # upload tests don't have to opt in to the new --force / batch
    # skip-and-continue surface. Tests that exercise the conflict path
    # override this with `monkeypatch.setattr(cli, '_remote_exists', ...)`.
    monkeypatch.setattr(cli, "_remote_exists", lambda *a, **k: False)


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


def test_put_refuses_overwrite_without_force(monkeypatch, tmp_path):
    """Single-file put against an existing remote item raises ConflictError
    (exit 15) so callers learn they need --force; the preflight saves
    the upload bytes when the remote is already there."""
    from owa_core.errors import ConflictError
    monkeypatch.setattr(cli, "_remote_exists", lambda *a, **k: True)
    monkeypatch.setattr(
        cli.api_mod, "api_put_binary",
        lambda *a, **k: pytest.fail("upload attempted despite existing remote"),
    )
    src = tmp_path / "upload.txt"
    src.write_bytes(b"upload")
    with pytest.raises(ConflictError, match="--force to overwrite"):
        cli.cmd_put(
            [str(src), "/Documents/upload.txt"],
            {}, "tok", "https://graph.test",
        )


def test_put_force_overwrites_existing(monkeypatch, tmp_path, capfd):
    monkeypatch.setattr(cli, "_remote_exists", lambda *a, **k: True)
    monkeypatch.setattr(
        cli.api_mod, "api_put_binary",
        lambda *a, **k: _drive_item("upload.txt"),
    )
    src = tmp_path / "upload.txt"
    src.write_bytes(b"upload")
    assert cli.cmd_put(
        [str(src), "/Documents/upload.txt", "--force"],
        {}, "tok", "https://graph.test",
    ) == 0
    assert json.loads(capfd.readouterr().out)["name"] == "upload.txt"


def test_get_refuses_clobber_without_force(monkeypatch, tmp_path):
    """get --out into an existing local file raises ConflictError (exit 15)
    so a download can't silently overwrite local data."""
    from owa_core.errors import ConflictError
    monkeypatch.setattr(
        cli.api_mod, "api_get_binary",
        lambda *a, **k: pytest.fail("download attempted despite existing file"),
    )
    out = tmp_path / "exists.txt"
    out.write_bytes(b"keep me")
    with pytest.raises(ConflictError, match="--force to overwrite"):
        cli.cmd_get(
            ["/Documents/report.txt", "--out", str(out)],
            {}, "tok", "https://graph.test",
        )
    assert out.read_bytes() == b"keep me"


def test_get_force_overwrites_local(monkeypatch, tmp_path, capfd):
    monkeypatch.setattr(cli.api_mod, "api_get_binary", lambda *a, **k: b"new")
    out = tmp_path / "exists.txt"
    out.write_bytes(b"old")
    assert cli.cmd_get(
        ["/Documents/report.txt", "--out", str(out), "--force"],
        {}, "tok", "https://graph.test",
    ) == 0
    assert out.read_bytes() == b"new"


def test_put_batch_skips_existing_uploads_rest(monkeypatch, tmp_path, capfd):
    """The headline batch contract: an existing remote file MUST NOT
    abort the upload of the other files. Skips and successes coexist
    in one JSON summary; exit 0 because no upload genuinely failed."""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    c = tmp_path / "c.txt"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    c.write_bytes(b"c")

    def fake_exists(api_base, remote, token, debug):
        return remote.endswith("/b.txt")  # only b.txt already exists

    monkeypatch.setattr(cli, "_remote_exists", fake_exists)
    uploaded = []

    def fake_put(api_base, endpoint, token, data, debug=False):
        uploaded.append(endpoint)
        return _drive_item(endpoint.rsplit("/", 1)[-1].split(":")[0])

    monkeypatch.setattr(cli.api_mod, "api_put_binary", fake_put)

    rc = cli.cmd_put(
        [str(a), str(b), str(c), "/Documents"],
        {}, "tok", "https://graph.test",
    )
    assert rc == 0
    out = json.loads(capfd.readouterr().out)
    uploaded_remotes = {entry["remote"] for entry in out["uploaded"]}
    skipped_remotes = {entry["remote"] for entry in out["skipped"]}
    assert uploaded_remotes == {"/Documents/a.txt", "/Documents/c.txt"}
    assert skipped_remotes == {"/Documents/b.txt"}
    assert out["failed"] == []


def test_put_batch_per_file_failure_does_not_abort(monkeypatch, tmp_path, capfd):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_bytes(b"a")
    b.write_bytes(b"b")

    calls = []

    def fake_put(api_base, endpoint, token, data, debug=False):
        calls.append(endpoint)
        if endpoint.endswith("/a.txt:/content"):
            # Production api_put_binary RAISES recoverable OwaErrors (it does
            # not return None); batch mode must catch and continue.
            raise cli.NetworkError("upload failed: connection reset")
        return _drive_item(endpoint.rsplit("/", 1)[-1])

    monkeypatch.setattr(cli.api_mod, "api_put_binary", fake_put)

    rc = cli.cmd_put(
        [str(a), str(b), "/Documents"],
        {}, "tok", "https://graph.test",
    )
    # Exit 1 because one upload failed, but the second was still tried.
    assert rc == 1
    out = json.loads(capfd.readouterr().out)
    assert len(calls) == 2
    assert {e["remote"] for e in out["uploaded"]} == {"/Documents/b.txt"}
    assert {e["remote"] for e in out["failed"]} == {"/Documents/a.txt"}


def test_put_batch_force_overwrites_all(monkeypatch, tmp_path, capfd):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_bytes(b"a")
    b.write_bytes(b"b")

    monkeypatch.setattr(
        cli, "_remote_exists",
        lambda *args, **kw: pytest.fail("preflight should be skipped with --force"),
    )
    monkeypatch.setattr(
        cli.api_mod, "api_put_binary",
        lambda api_base, endpoint, token, data, **kw: _drive_item("x"),
    )

    rc = cli.cmd_put(
        [str(a), str(b), "/Documents", "--force"],
        {}, "tok", "https://graph.test",
    )
    assert rc == 0
    out = json.loads(capfd.readouterr().out)
    assert len(out["uploaded"]) == 2
    assert out["skipped"] == []
    assert out["failed"] == []


def test_put_batch_stdin_is_rejected(tmp_path):
    """stdin in batch mode has no basename to map to <remote-dir>/<name>."""
    a = tmp_path / "a.txt"
    a.write_bytes(b"a")
    with pytest.raises(cli.UsageError, match="stdin"):
        cli.cmd_put(["-", str(a), "/Documents"], {}, "tok", "https://graph.test")


def test_drive_validation_confirm_and_failures(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.api_mod, "api_get_binary", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.api_mod, "api_put_binary", lambda *args, **kwargs: None)

    assert cli.cmd_ls([], {}, "tok", "https://graph.test") == 1
    with pytest.raises(cli.UsageError, match='show requires'):
        cli.cmd_show([], {}, "tok", "https://graph.test")
    with pytest.raises(cli.UsageError, match='get requires'):
        cli.cmd_get([], {}, "tok", "https://graph.test")
    assert cli.cmd_get(["/"], {}, "tok", "https://graph.test") == 1
    assert "root has no content" in capsys.readouterr().err
    with pytest.raises(cli.UsageError, match='put requires'):
        cli.cmd_put([], {}, "tok", "https://graph.test")
    assert cli.cmd_put([str(tmp_path / "missing"), "/x"], {}, "tok", "https://graph.test") == 1
    assert "cannot read" in capsys.readouterr().err
    monkeypatch.setattr(cli.sys, "stdin", type("Stdin", (), {"buffer": io.BytesIO(b"stdin-data")})())
    assert cli.cmd_put(["-", "/"], {}, "tok", "https://graph.test") == 1
    assert "root has no content" in capsys.readouterr().err
    with pytest.raises(cli.UsageError, match='rm requires'):
        cli.cmd_rm([], {}, "tok", "https://graph.test")
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
