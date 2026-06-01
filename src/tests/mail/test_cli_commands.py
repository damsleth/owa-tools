"""Direct command tests for owa-mail."""

import io
import json

import pytest

from owa_mail import cli


def _raw_message(msg_id="m1", subject="Hello"):
    return {
        "Id": msg_id,
        "ConversationId": "c1",
        "ReceivedDateTime": "2026-05-09T10:00:00Z",
        "SentDateTime": "2026-05-09T09:59:00Z",
        "Subject": subject,
        "From": {"EmailAddress": {"Address": "ada@example.com"}},
        "ToRecipients": [{"EmailAddress": {"Address": "bob@example.com"}}],
        "BodyPreview": "preview",
        "Body": {"ContentType": "Text", "Content": "body"},
        "IsRead": False,
        "HasAttachments": False,
        "Importance": "Normal",
        "Flag": {"FlagStatus": "NotFlagged"},
        "ParentFolderId": "inbox",
    }


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})
    monkeypatch.setattr(cli.auth_mod, "setup_auth", lambda config, debug=False: ("tok", "https://outlook.test"))


def test_main_schema_globals_and_split(capsys, monkeypatch):
    assert cli._split_globals(["--debug", "--profile", "work", "messages"]) == (
        True,
        "work",
        ["messages"],
        None,
    )
    assert cli._split_globals(["config", "--profile", "work"])[2] == ["config", "--profile", "work"]
    assert cli._split_globals(["--profile"])[3] == "--profile requires a value"

    assert cli._main(["schema"]) == 0
    assert json.loads(capsys.readouterr().out)["tool"] == "owa-mail"

    seen = {}

    def fake_auth(config, debug=False):
        seen["config"] = dict(config)
        seen["debug"] = debug
        return "tok", "https://outlook.test"

    monkeypatch.setattr(cli.auth_mod, "setup_auth", fake_auth)
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *args, **kwargs: {"value": []})
    assert cli._main(["--debug", "--profile", "work", "messages"]) == 0
    assert seen["config"]["debug"] is True
    assert seen["config"]["owa_piggy_profile"] == "work"
    assert seen["debug"] is True


def test_messages_show_folders_and_validation(monkeypatch, capsys):
    get_calls = []

    def fake_get(api_base, endpoint, access_token, **kwargs):
        get_calls.append((api_base, endpoint, access_token, kwargs))
        if endpoint.startswith("me/MailFolders?"):
            return {"value": [{"Id": "Inbox", "DisplayName": "Inbox", "UnreadItemCount": 1, "TotalItemCount": 2}]}
        if endpoint.startswith("me/messages/"):
            return _raw_message()
        return {"value": [_raw_message()]}

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)

    assert cli.cmd_messages([
        "--folder",
        "Inbox",
        "--unread",
        "--from",
        "ada",
        "--subject",
        "hello",
        "--since",
        "2026-05-01",
        "--until",
        "2026-05-09",
        "--limit",
        "999",
    ], {}, "tok", "https://outlook.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["subject"] == "Hello"
    assert "$top=200" in get_calls[-1][1]
    assert "IsRead%20eq%20false" in get_calls[-1][1]

    with pytest.raises(cli.UsageError, match='--search cannot be combined'):
        cli.cmd_messages(["--search", "hello", "--unread"], {}, "tok", "https://outlook.test")
    with pytest.raises(cli.UsageError, match='--limit must be'):
        cli.cmd_messages(["--limit", "0"], {}, "tok", "https://outlook.test")
    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    assert cli.cmd_show(["--id", "m1", "--pretty"], {}, "tok", "https://outlook.test") == 0
    assert "Hello" in capsys.readouterr().out
    with pytest.raises(cli.UsageError, match='--id is required'):
        cli.cmd_show([], {}, "tok", "https://outlook.test")

    assert cli.cmd_folders(["--pretty"], {}, "tok", "https://outlook.test") == 0
    assert "Inbox" in capsys.readouterr().out
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *args, **kwargs: None)
    assert cli.cmd_folders([], {}, "tok", "https://outlook.test") == 1

    with pytest.raises(cli.UsageError, match='--search cannot be combined'):
        cli.cmd_messages(["--search", "hello", "--unread"], {}, "tok", "https://outlook.test")
    with pytest.raises(cli.UsageError, match='--limit must be'):
        cli.cmd_messages(["--limit", "0"], {}, "tok", "https://outlook.test")
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *args, **kwargs: None)
    assert cli.cmd_messages([], {}, "tok", "https://outlook.test") == 1


def test_messages_search_json_is_newest_first(monkeypatch, capsys):
    # $search drops $orderby (mutually exclusive), so the API returns relevance
    # order. cmd_messages must restore newest-first for JSON consumers.
    out_of_order = {"value": [
        _raw_message("old", "Older"),
        _raw_message("new", "Newer"),
    ]}
    out_of_order["value"][0]["ReceivedDateTime"] = "2026-05-01T10:00:00Z"
    out_of_order["value"][1]["ReceivedDateTime"] = "2026-05-09T10:00:00Z"
    sent_endpoints = []

    def fake_get(api_base, endpoint, access_token, **kwargs):
        sent_endpoints.append(endpoint)
        return out_of_order

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    assert cli.cmd_messages(["--search", "budget"], {}, "tok", "https://outlook.test") == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["new", "old"]  # newest first despite API order
    assert "%24orderby" not in sent_endpoints[-1]  # no $orderby sent with $search


def test_show_html_body_pretty_vs_json(monkeypatch, capsys):
    raw = _raw_message("h1", "HTML mail")
    raw["Body"] = {
        "ContentType": "HTML",
        "Content": "<p>Hello <b>world</b></p><script>evil()</script>",
    }
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: raw)

    # JSON path: body is emitted verbatim (still raw HTML, not converted).
    assert cli.cmd_show(["--id", "h1"], {}, "tok", "https://outlook.test") == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["body"] == "<p>Hello <b>world</b></p><script>evil()</script>"
    assert obj["body_type"] == "HTML"

    # --pretty path: body is flattened to readable text, script dropped.
    assert cli.cmd_show(["--id", "h1", "--pretty"], {}, "tok", "https://outlook.test") == 0
    pretty = capsys.readouterr().out
    assert "Hello world" in pretty
    assert "<p>" not in pretty
    assert "evil()" not in pretty


def test_send_reply_forward_move_mark_delete(monkeypatch, capsys):
    calls = []

    def fake_request(method, api_base, endpoint, access_token, **kwargs):
        calls.append((method, endpoint, kwargs.get("body")))
        if endpoint.endswith("/sendMail") or endpoint.endswith("/send"):
            return {}
        if method == "DELETE":
            return {}
        if endpoint.endswith("/move"):
            return _raw_message("m2", "Moved")
        if method == "PATCH":
            return _raw_message("draft-1", "Patched")
        return _raw_message("draft-1", "Draft")

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *args, **kwargs: _raw_message("draft-1", "Saved"))

    assert cli.cmd_send([
        "--to",
        "bob@example.com",
        "--cc",
        "cc@example.com",
        "--bcc",
        "bcc@example.com",
        "--subject",
        "Hi",
        "--body",
        "Hello",
        "--html",
        "--importance",
        "high",
    ], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out) == {"sent": True}
    assert calls[-1][1] == "me/sendMail"

    assert cli.cmd_send([
        "--to",
        "bob@example.com",
        "--subject",
        "Later",
        "--send-at",
        "2026-05-09T12:00:00Z",
    ], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["send_at"] == "2026-05-09T12:00:00Z"
    assert calls[-2][1] == "me/messages"
    assert calls[-1][1] == "me/messages/draft-1/send"

    assert cli.cmd_send(["--to", "bob@example.com", "--subject", "Draft", "--save-draft"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["id"] == "draft-1"

    assert cli.cmd_reply(["--id", "m1", "--body", "thanks"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["sent"] is True
    assert cli.cmd_reply_all(["--id", "m1", "--save-draft"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["id"] == "draft-1"
    assert cli.cmd_forward(["--id", "m1", "--to", "c@example.com", "--body", "fwd"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["id"] == "draft-1"

    with pytest.raises(cli.UsageError, match='forward requires --to'):
        cli.cmd_forward(["--id", "m1", "--body", "fwd"], {}, "tok", "https://outlook.test")
    with pytest.raises(cli.UsageError, match='--body is required'):
        cli.cmd_reply(["--id", "m1"], {}, "tok", "https://outlook.test")

    assert cli.cmd_move(["--id", "m1", "--to", "Archive"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["subject"] == "Moved"
    assert cli.cmd_mark(["--id", "m1", "--read", "--flag"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["subject"] == "Patched"
    with pytest.raises(cli.UsageError, match='mark requires'):
        cli.cmd_mark(["--id", "m1"], {}, "tok", "https://outlook.test")
    with pytest.raises(cli.UsageError, match='mutually exclusive'):
        cli.cmd_mark(["--id", "m1", "--read", "--unread"], {}, "tok", "https://outlook.test")

    assert cli.cmd_delete(["--id", "m1", "--confirm"], {}, "tok", "https://outlook.test") == 0
    assert "Deleted." in capsys.readouterr().err

    monkeypatch.setattr(cli.tty_mod, "require_confirm_or_tty", lambda action: None)
    monkeypatch.setattr(cli.tty_mod, "confirm", lambda prompt: False)
    assert cli.cmd_delete(["--id", "m1"], {}, "tok", "https://outlook.test") == 0
    assert "Aborted." in capsys.readouterr().err


def test_send_stdin_invalid_and_api_failures(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("from stdin"))
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *args, **kwargs: {})
    assert cli.cmd_send(["--to", "bob@example.com", "--subject", "Hi", "--body", "-"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)["sent"] is True

    with pytest.raises(cli.UsageError, match='invalid importance'):
        cli.cmd_send(["--to", "bob@example.com", "--subject", "Hi", "--importance", "urgent"], {}, "tok", "https://outlook.test")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *args, **kwargs: None)
    assert cli.cmd_send(["--to", "bob@example.com", "--subject", "Hi"], {}, "tok", "https://outlook.test") == 1
    assert cli.cmd_move(["--id", "m1", "--to", "Archive"], {}, "tok", "https://outlook.test") == 1
    assert cli.cmd_delete(["--id", "m1", "--confirm"], {}, "tok", "https://outlook.test") == 1


def test_mail_config_and_refresh(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, "CONFIG_PATH", "/tmp/owa-mail-config")
    monkeypatch.setattr(cli.config_mod, "config_set", lambda key, value: saved.setdefault(key, value))

    assert cli.cmd_config([], {"owa_piggy_profile": "work"}) == 0
    assert "owa_piggy_profile=work" in capsys.readouterr().err
    assert cli.cmd_config(["--profile", "home"], {}) == 0
    assert saved["owa_piggy_profile"] == "home"

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *args, **kwargs: {"DisplayName": "Ada"})
    assert cli.cmd_refresh([], {}) == 0
    assert "Authenticated as Ada" in capsys.readouterr().err

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "")
    assert cli.cmd_refresh([], {}) == 1
    assert "Token refresh failed" in capsys.readouterr().err

    monkeypatch.setattr(cli.auth_mod, "do_token_refresh", lambda config, debug=False: "tok")
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *args, **kwargs: None)
    assert cli.cmd_refresh([], {}) == 1
    assert "Auth verification failed" in capsys.readouterr().err

    with pytest.raises(cli.UsageError, match="Unknown flag"):
        cli.cmd_refresh(["--bogus"], {})
