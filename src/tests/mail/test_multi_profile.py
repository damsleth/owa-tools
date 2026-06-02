"""In-process multi-profile fan-out for owa-mail with mocked auth.

The broker-missing subprocess tests in ``tests/contract/test_multi_profile_fanout.py``
cover the all-fail path for every tool. This module mocks the auth + HTTP seam
so the *success* and *mixed* merges run through the real ``owa_mail.main()`` ->
``run_with_output_modes`` -> ``_main`` wiring, proving per-profile data is
isolated and keyed correctly.
"""
import json

from owa_core.errors import AuthExpiredError
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


def _mock_token_per_profile(monkeypatch):
    """setup_auth returns a token encoding the active profile, so the HTTP
    mock can return per-profile data."""
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})

    def fake_auth(config, debug=False):
        profile = config.get("owa_piggy_profile", "")
        return f"tok-{profile}", "https://outlook.test"

    monkeypatch.setattr(cli.auth_mod, "setup_auth", fake_auth)


def test_fan_out_success_merges_per_profile_data(monkeypatch, capsys):
    _mock_token_per_profile(monkeypatch)

    def fake_get(api_base, endpoint, access_token, **kwargs):
        # cmd_messages issues a single GET to the messages path; the token
        # encodes the active profile so each run returns its own data.
        profile = access_token.removeprefix("tok-")
        return {"value": [_raw_message(msg_id=f"id-{profile}", subject=f"hi-{profile}")]}

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)

    rc = cli.main(["--profile", "a", "--profile", "b", "messages"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["_owa"]["tool"] == "owa-mail"
    assert payload["_owa"]["command"] == "messages"
    assert payload["_owa"]["profiles"] == ["a", "b"]

    results = payload["results"]
    assert [r["profile"] for r in results] == ["a", "b"]
    assert all(r["ok"] for r in results)
    # Each profile's run saw its own token and returned its own data.
    assert results[0]["data"][0]["subject"] == "hi-a"
    assert results[1]["data"][0]["subject"] == "hi-b"


def test_fan_out_mixed_isolates_failure_and_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})

    def fake_auth(config, debug=False):
        profile = config.get("owa_piggy_profile", "")
        if profile == "b":
            raise AuthExpiredError("no token for b")
        return f"tok-{profile}", "https://outlook.test"

    monkeypatch.setattr(cli.auth_mod, "setup_auth", fake_auth)
    monkeypatch.setattr(
        cli.api_mod,
        "api_get",
        lambda api_base, endpoint, access_token, **kwargs: {
            "value": [_raw_message(subject="ok")]
        },
    )

    rc = cli.main(["--profile", "a", "--profile", "b", "messages"])

    # One ok, one failed -> mixed -> exit 2.
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    results = payload["results"]
    assert results[0]["profile"] == "a"
    assert results[0]["ok"] is True
    assert results[1]["profile"] == "b"
    assert results[1]["ok"] is False
    assert results[1]["exit_code"] == 11
    assert "no token for b" in results[1]["error"]
