"""CLI tests for owa-mail attachment read/send surfaces."""

import base64
import json

import pytest

from owa_mail import cli


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth",
        lambda config, debug=False: ("tok", "https://outlook.test"),
    )


def _attachments_payload():
    return {
        "value": [
            {
                "@odata.type": "#Microsoft.OutlookServices.FileAttachment",
                "Id": "att-1",
                "Name": "report.pdf",
                "ContentType": "application/pdf",
                "Size": 12345,
                "IsInline": False,
            }
        ]
    }


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def test_attachments_list_json_and_pretty(monkeypatch, capsys):
    seen = {}

    def fake_get(api_base, endpoint, token, **kwargs):
        seen["endpoint"] = endpoint
        return _attachments_payload()

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)

    assert cli.cmd_attachments(["--id", "m1"], {}, "tok", "https://outlook.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["name"] == "report.pdf"
    assert rows[0]["size"] == 12345
    assert "ContentBytes" not in seen["endpoint"]
    # Listing must not request base64 content.
    assert "ContentBytes" not in seen["endpoint"]
    assert seen["endpoint"].startswith("me/messages/m1/attachments?")

    assert cli.cmd_attachments(["--id", "m1", "--pretty"], {}, "tok", "https://outlook.test") == 0
    out = capsys.readouterr().out
    assert "report.pdf" in out
    assert "application/pdf" in out


def test_attachments_requires_id_and_handles_failure(monkeypatch):
    with pytest.raises(cli.UsageError, match='--id is required'):
        cli.cmd_attachments([], {}, "tok", "https://outlook.test")
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_attachments(["--id", "m1"], {}, "tok", "https://outlook.test") == 1
    with pytest.raises(cli.UsageError):
        cli.cmd_attachments(["--bogus"], {}, "tok", "https://outlook.test")


def test_attachment_get_to_file_and_stdout(monkeypatch, tmp_path, capfd):
    seen = {}

    def fake_binary(api_base, endpoint, token, **kwargs):
        seen["endpoint"] = endpoint
        return b"PNGdata"

    monkeypatch.setattr(cli.api_mod, "api_get_binary", fake_binary)

    out = tmp_path / "img.png"
    assert cli.cmd_attachment_get(
        ["--id", "m1", "--attachment", "att-1", "--out", str(out)],
        {}, "tok", "https://outlook.test",
    ) == 0
    assert out.read_bytes() == b"PNGdata"
    assert "wrote 7 bytes" in capfd.readouterr().err
    assert seen["endpoint"] == "me/messages/m1/attachments/att-1/$value"

    assert cli.cmd_attachment_get(
        ["--id", "m1", "--attachment", "att-1"],
        {}, "tok", "https://outlook.test",
    ) == 0
    assert capfd.readouterr().out == "PNGdata"


def test_attachment_get_validation_and_failure(monkeypatch):
    with pytest.raises(cli.UsageError, match='--id is required'):
        cli.cmd_attachment_get([], {}, "tok", "https://outlook.test")
    with pytest.raises(cli.UsageError, match='--attachment is required'):
        cli.cmd_attachment_get(["--id", "m1"], {}, "tok", "https://outlook.test")
    monkeypatch.setattr(cli.api_mod, "api_get_binary", lambda *a, **k: None)
    assert cli.cmd_attachment_get(
        ["--id", "m1", "--attachment", "a"], {}, "tok", "https://outlook.test",
    ) == 1
    with pytest.raises(cli.UsageError):
        cli.cmd_attachment_get(["--bogus"], {}, "tok", "https://outlook.test")


# --------------------------------------------------------------------------
# Sending: small (inline) path
# --------------------------------------------------------------------------

def test_send_small_attachment_inline(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_request(method, api_base, endpoint, token, **kwargs):
        calls.append((method, endpoint, kwargs.get("body")))
        return {}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)

    f = tmp_path / "note.txt"
    f.write_bytes(b"small file")

    assert cli.cmd_send(
        ["--to", "bob@x.com", "--subject", "Hi", "--body", "see file", "--attach", str(f)],
        {}, "tok", "https://outlook.test",
    ) == 0
    assert json.loads(capsys.readouterr().out) == {"sent": True}
    # Inline path: single sendMail, no createUploadSession.
    assert calls[-1][1] == "me/sendMail"
    msg = calls[-1][2]["Message"]
    inline = msg["Attachments"][0]
    assert inline["Name"] == "note.txt"
    assert base64.b64decode(inline["ContentBytes"]) == b"small file"


def test_send_missing_attachment_file(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: pytest.fail("no request expected"))
    assert cli.cmd_send(
        ["--to", "bob@x.com", "--subject", "Hi", "--body", "x", "--attach", str(tmp_path / "nope.txt")],
        {}, "tok", "https://outlook.test",
    ) == 1
    assert "attachment not found" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Sending: large (upload-session) path
# --------------------------------------------------------------------------

def test_send_large_attachment_uses_draft_and_session(monkeypatch, tmp_path, capsys):
    calls = []
    session_calls = []

    def fake_request(method, api_base, endpoint, token, **kwargs):
        calls.append((method, endpoint, kwargs.get("body")))
        if endpoint == "me/messages":
            return {"Id": "draft-9"}
        return {}

    def fake_session(api_base, endpoint, token, body, content, **kwargs):
        session_calls.append((endpoint, body, len(content)))
        return {"id": "att-up"}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    monkeypatch.setattr(cli.api_mod, "api_upload_attachment_session", fake_session)

    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * (cli.attachments_mod.INLINE_LIMIT_BYTES + 1))

    assert cli.cmd_send(
        ["--to", "bob@x.com", "--subject", "Big", "--body", "huge", "--attach", str(big)],
        {}, "tok", "https://outlook.test",
    ) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["sent"] is True and out["id"] == "draft-9"
    # Draft created, upload session used, then draft sent.
    methods = [c[1] for c in calls]
    assert "me/messages" in methods
    assert "me/messages/draft-9/send" in methods
    assert "me/sendMail" not in methods
    assert session_calls[0][0] == "me/messages/draft-9/attachments/createUploadSession"
    assert session_calls[0][1]["AttachmentItem"]["size"] == cli.attachments_mod.INLINE_LIMIT_BYTES + 1
    assert session_calls[0][2] == cli.attachments_mod.INLINE_LIMIT_BYTES + 1


def test_send_large_attachment_session_failure_returns_one(monkeypatch, tmp_path):
    def fake_request(method, api_base, endpoint, token, **kwargs):
        if endpoint == "me/messages":
            return {"Id": "draft-9"}
        return {}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    monkeypatch.setattr(cli.api_mod, "api_upload_attachment_session", lambda *a, **k: None)

    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * (cli.attachments_mod.INLINE_LIMIT_BYTES + 1))
    assert cli.cmd_send(
        ["--to", "bob@x.com", "--subject", "Big", "--body", "x", "--attach", str(big)],
        {}, "tok", "https://outlook.test",
    ) == 1


# --------------------------------------------------------------------------
# Reply / forward with attachments
# --------------------------------------------------------------------------

def test_reply_with_small_attachment_posts_inline(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_request(method, api_base, endpoint, token, **kwargs):
        calls.append((method, endpoint, kwargs.get("body")))
        if endpoint.endswith("/createReply"):
            return {"Id": "draft-r"}
        return {}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)

    f = tmp_path / "a.txt"
    f.write_bytes(b"hi")
    assert cli.cmd_reply(
        ["--id", "m1", "--body", "thanks", "--attach", str(f)],
        {}, "tok", "https://outlook.test",
    ) == 0
    assert json.loads(capsys.readouterr().out)["sent"] is True
    # Attachment POSTed to the draft's attachments collection.
    post_atts = [c for c in calls if c[1] == "me/messages/draft-r/attachments"]
    assert len(post_atts) == 1
    assert post_atts[0][2]["Name"] == "a.txt"
    assert calls[-1][1] == "me/messages/draft-r/send"


def test_forward_with_large_attachment_uses_session(monkeypatch, tmp_path, capsys):
    session_calls = []

    def fake_request(method, api_base, endpoint, token, **kwargs):
        if endpoint.endswith("/createForward"):
            return {"Id": "draft-f"}
        return {}

    def fake_session(api_base, endpoint, token, body, content, **kwargs):
        session_calls.append(endpoint)
        return {"id": "att-up"}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    monkeypatch.setattr(cli.api_mod, "api_upload_attachment_session", fake_session)

    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * (cli.attachments_mod.INLINE_LIMIT_BYTES + 1))
    assert cli.cmd_forward(
        ["--id", "m1", "--to", "c@x.com", "--attach", str(big)],
        {}, "tok", "https://outlook.test",
    ) == 0
    assert json.loads(capsys.readouterr().out)["sent"] is True
    assert session_calls == ["me/messages/draft-f/attachments/createUploadSession"]


def test_reply_attachment_only_no_body_allowed(monkeypatch, tmp_path, capsys):
    def fake_request(method, api_base, endpoint, token, **kwargs):
        if endpoint.endswith("/createReply"):
            return {"Id": "draft-r"}
        return {}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    f = tmp_path / "a.txt"
    f.write_bytes(b"hi")
    # No --body, but an attachment is enough to proceed.
    assert cli.cmd_reply(
        ["--id", "m1", "--attach", str(f)], {}, "tok", "https://outlook.test",
    ) == 0
    assert json.loads(capsys.readouterr().out)["sent"] is True


def test_reply_attachment_missing_file(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: pytest.fail("no request"))
    assert cli.cmd_reply(
        ["--id", "m1", "--body", "x", "--attach", str(tmp_path / "nope.txt")],
        {}, "tok", "https://outlook.test",
    ) == 1
    assert "attachment not found" in capsys.readouterr().err
