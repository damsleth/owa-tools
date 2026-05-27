"""owa-drive accepts suite-canonical aliases (list/download/upload/delete)
for its unix verbs (ls/get/put/rm). No network."""

import pytest

from owa_drive import cli


@pytest.fixture(autouse=True)
def _stub(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth",
        lambda config, debug=False: ("tok", "https://graph.test"),
    )


def test_list_alias_matches_ls(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: {"value": []})
    assert cli._main(["ls", "/Documents"]) == 0
    ls_out = capsys.readouterr().out
    assert cli._main(["list", "/Documents"]) == 0
    assert capsys.readouterr().out == ls_out


def test_delete_alias_routes_to_rm(monkeypatch):
    seen = {}

    def fake_request(method, *a, **k):
        seen["method"] = method
        return {}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli._main(["delete", "/Documents/x.txt", "--confirm"]) == 0
    assert seen["method"] == "DELETE"


def test_download_alias_routes_to_get(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.api_mod, "api_get_binary", lambda *a, **k: b"hello-bytes")
    out = tmp_path / "x.txt"
    assert cli._main(["download", "/Documents/x.txt", "--out", str(out)]) == 0
    assert out.read_bytes() == b"hello-bytes"


def test_upload_alias_routes_to_put(monkeypatch, tmp_path):
    src = tmp_path / "x.txt"
    src.write_bytes(b"hi")
    seen = {}
    monkeypatch.setattr(
        cli.api_mod, "api_put_binary",
        lambda *a, **k: seen.setdefault("put", True) or {"id": "1", "name": "x.txt", "size": 2},
    )
    assert cli._main(["upload", str(src), "/Documents/x.txt"]) == 0
    assert seen.get("put")


def test_alias_help_shows_canonical_usage(capsys):
    assert cli._main(["delete", "--help"]) == 0
    out = capsys.readouterr().out
    assert "owa-drive rm" in out
    assert "Aliases: delete" in out
