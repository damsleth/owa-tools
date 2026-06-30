"""CLI + pure-function tests for owa-mail P2 features.

Covers: attachment-get item/reference fallback, move/copy by folder
display name, --orderby/--skip passthrough, categories set + filter,
--has-attachments/--importance filters, and the thread/conversation
command. No network, no real tokens (stubbed like the rest of the suite).
"""
import json

import pytest

from owa_core.errors import NotFoundError
from owa_mail import attachments as attachments_mod
from owa_mail import cli
from owa_mail import folders as folders_mod
from owa_mail import messages as messages_mod


@pytest.fixture(autouse=True)
def _stub_config_and_auth(monkeypatch):
    monkeypatch.setattr(cli.config_mod, "load_config", lambda: {})
    monkeypatch.setattr(
        cli.auth_mod, "setup_auth",
        lambda config, debug=False: ("tok", "https://outlook.test"),
    )


# ---------------------------------------------------------------------------
# build_list_query: orderby / skip / category / has-attachments / importance
# ---------------------------------------------------------------------------

def test_build_list_query_skip_and_orderby():
    params = messages_mod.build_list_query(skip=25, orderby="Subject asc")
    assert params["$skip"] == 25
    assert params["$orderby"] == "Subject asc"


def test_build_list_query_orderby_wins_over_default():
    # An explicit orderby is kept even with no filters.
    params = messages_mod.build_list_query(orderby="ReceivedDateTime asc")
    assert params["$orderby"] == "ReceivedDateTime asc"


def test_build_list_query_category_filter_drops_default_orderby():
    params = messages_mod.build_list_query(category="Red")
    assert "$orderby" not in params
    assert params["$filter"] == "Categories/any(c:c eq 'Red')"


def test_build_list_query_category_escapes_quotes():
    params = messages_mod.build_list_query(category="O'Brien")
    assert "c eq 'O''Brien'" in params["$filter"]


def test_build_list_query_has_attachments_and_importance():
    params = messages_mod.build_list_query(has_attachments=True, importance="high")
    assert "HasAttachments eq true" in params["$filter"]
    assert "Importance eq 'High'" in params["$filter"]
    assert "$orderby" not in params


def test_build_list_query_bad_importance_raises():
    with pytest.raises(ValueError, match="invalid importance"):
        messages_mod.build_list_query(importance="urgent")


def test_normalize_message_surfaces_categories():
    flat = messages_mod.normalize_message({"Id": "m1", "Categories": ["Red", "Urgent", 1]})
    assert flat["categories"] == ["Red", "Urgent"]


# ---------------------------------------------------------------------------
# messages CLI: new filter flags
# ---------------------------------------------------------------------------

def test_messages_filter_flags_compose(monkeypatch, capsys):
    seen = {}

    def fake_get(api_base, endpoint, token, **kwargs):
        seen["endpoint"] = endpoint
        return {"value": []}

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    assert cli.cmd_messages(
        ["--category", "Red", "--has-attachments", "--importance", "high",
         "--skip", "10", "--orderby", "Subject asc"],
        {}, "tok", "https://outlook.test",
    ) == 0
    ep = seen["endpoint"]
    assert "$skip=10" in ep
    assert "Subject%20asc" in ep
    assert "HasAttachments%20eq%20true" in ep
    assert "Importance%20eq%20%27High%27" in ep


def test_messages_search_conflicts_with_category(monkeypatch):
    with pytest.raises(cli.UsageError, match="search cannot be combined"):
        cli.cmd_messages(
            ["--search", "x", "--category", "Red"], {}, "tok", "https://outlook.test",
        )


def test_messages_bad_importance_is_usage_error(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {"value": []})
    with pytest.raises(cli.UsageError, match="invalid importance"):
        cli.cmd_messages(["--importance", "urgent"], {}, "tok", "https://outlook.test")


def test_messages_negative_skip_rejected():
    with pytest.raises(cli.UsageError, match="skip must be >= 0"):
        cli.cmd_messages(["--skip", "-1"], {}, "tok", "https://outlook.test")


# ---------------------------------------------------------------------------
# attachment-get: item/reference fallback
# ---------------------------------------------------------------------------

def test_attachment_get_item_fallback_json(monkeypatch, capsys):
    def fake_binary(*a, **k):
        raise NotFoundError("no $value")

    def fake_get(api_base, endpoint, token, **kwargs):
        assert endpoint == "me/messages/m1/attachments/att-2"
        return {
            "@odata.type": "#microsoft.graph.itemAttachment",
            "Id": "att-2", "Name": "Embedded", "Size": 99,
            "Item": {"subject": "inner"},
        }

    monkeypatch.setattr(cli.api_mod, "api_get_binary", fake_binary)
    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    rc = cli.cmd_attachment_get(
        ["--id", "m1", "--attachment", "att-2"], {}, "tok", "https://outlook.test",
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "itemAttachment"
    assert out["item"] == {"subject": "inner"}


def test_attachment_get_reference_fallback_to_file(monkeypatch, tmp_path, capsys):
    def fake_binary(*a, **k):
        raise NotFoundError("no $value")

    monkeypatch.setattr(cli.api_mod, "api_get_binary", fake_binary)
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {
        "@odata.type": "#microsoft.graph.referenceAttachment",
        "Id": "ref-1", "Name": "doc", "SourceUrl": "https://x/doc",
    })
    out = tmp_path / "meta.json"
    rc = cli.cmd_attachment_get(
        ["--id", "m1", "--attachment", "ref-1", "--out", str(out)],
        {}, "tok", "https://outlook.test",
    )
    assert rc == 0
    written = json.loads(out.read_text())
    assert written["source_url"] == "https://x/doc"
    assert "metadata" in capsys.readouterr().err


def test_attachment_get_fallback_api_failure(monkeypatch):
    def fake_binary(*a, **k):
        raise NotFoundError("no $value")

    monkeypatch.setattr(cli.api_mod, "api_get_binary", fake_binary)
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_attachment_get(
        ["--id", "m1", "--attachment", "x"], {}, "tok", "https://outlook.test",
    ) == 1


def test_attachment_resource_pure():
    flat = attachments_mod.attachment_resource({
        "@odata.type": "#microsoft.graph.fileAttachment", "Id": "a", "Name": "n",
    })
    assert flat["kind"] == "fileAttachment"
    assert "item" not in flat and "source_url" not in flat
    assert attachments_mod.attachment_resource("nope") == {}


# ---------------------------------------------------------------------------
# move / copy by display name
# ---------------------------------------------------------------------------

def test_move_well_known_skips_lookup(monkeypatch):
    calls = []

    def fake_request(method, base, endpoint, token, body=None, **kwargs):
        calls.append((endpoint, body))
        return {"Id": "m1", "Subject": "Moved"}

    def fake_get(*a, **k):
        raise AssertionError("well-known move must not hit folder lookup")

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    assert cli.cmd_move(["--id", "m1", "--to", "Archive"], {}, "tok", "https://outlook.test") == 0
    assert calls[-1][0] == "me/messages/m1/move"
    assert calls[-1][1] == {"DestinationId": "Archive"}


def test_move_by_display_name_resolves_id(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {
        "value": [{"Id": "FOLDER123", "DisplayName": "Project X"}]
    })

    def fake_request(method, base, endpoint, token, body=None, **kwargs):
        calls.append((endpoint, body))
        return {"Id": "m1", "Subject": "Moved"}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli.cmd_move(["--id", "m1", "--to", "Project X"], {}, "tok", "https://outlook.test") == 0
    assert calls[-1][1] == {"DestinationId": "FOLDER123"}


def test_move_unknown_name_passes_through_as_id(monkeypatch):
    calls = []
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {"value": []})

    def fake_request(method, base, endpoint, token, body=None, **kwargs):
        calls.append(body)
        return {"Id": "m1", "Subject": "Moved"}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli.cmd_move(["--id", "m1", "--to", "AAMkOpaqueId"], {}, "tok", "https://outlook.test") == 0
    assert calls[-1] == {"DestinationId": "AAMkOpaqueId"}


def test_move_lookup_failure(monkeypatch):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_move(["--id", "m1", "--to", "Project X"], {}, "tok", "https://outlook.test") == 1


def test_copy_command(monkeypatch):
    calls = []

    def fake_request(method, base, endpoint, token, body=None, **kwargs):
        calls.append(endpoint)
        return {"Id": "m2", "Subject": "Copied"}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli.cmd_copy(["--id", "m1", "--to", "Archive"], {}, "tok", "https://outlook.test") == 0
    assert calls[-1] == "me/messages/m1/copy"


def test_move_requires_id_and_to():
    with pytest.raises(cli.UsageError, match="--id is required"):
        cli.cmd_move([], {}, "tok", "https://outlook.test")
    with pytest.raises(cli.UsageError, match="--to is required"):
        cli.cmd_move(["--id", "m1"], {}, "tok", "https://outlook.test")


# folders helpers (pure)

def test_folder_helpers():
    assert folders_mod.is_well_known("archive") is True
    assert folders_mod.is_well_known("Project X") is False
    assert folders_mod.is_well_known("") is True
    folders = [{"id": "F1", "name": "Project X"}, {"id": "F2", "name": "Other"}]
    assert folders_mod.pick_folder_id(folders, "project x") == "F1"
    assert folders_mod.pick_folder_id(folders, "missing") == ""
    assert "Project%20X" not in folders_mod.folder_lookup_query("Project X")["$filter"]


# ---------------------------------------------------------------------------
# categories command
# ---------------------------------------------------------------------------

def test_categories_set(monkeypatch, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, body=None, **kwargs):
        seen["method"] = method
        seen["body"] = body
        return {"Id": "m1", "Categories": ["Red", "Urgent"]}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli.cmd_categories(
        ["--id", "m1", "--category", "Red", "--category", "Urgent"],
        {}, "tok", "https://outlook.test",
    ) == 0
    assert seen["method"] == "PATCH"
    assert seen["body"] == {"Categories": ["Red", "Urgent"]}
    assert json.loads(capsys.readouterr().out)["categories"] == ["Red", "Urgent"]


def test_categories_clear(monkeypatch):
    seen = {}

    def fake_request(method, base, endpoint, token, body=None, **kwargs):
        seen["body"] = body
        return {"Id": "m1", "Categories": []}

    monkeypatch.setattr(cli.api_mod, "api_request", fake_request)
    assert cli.cmd_categories(["--id", "m1"], {}, "tok", "https://outlook.test") == 0
    assert seen["body"] == {"Categories": []}


def test_categories_requires_id_and_handles_failure(monkeypatch):
    with pytest.raises(cli.UsageError, match="--id is required"):
        cli.cmd_categories(["--category", "Red"], {}, "tok", "https://outlook.test")
    monkeypatch.setattr(cli.api_mod, "api_request", lambda *a, **k: None)
    assert cli.cmd_categories(["--id", "m1"], {}, "tok", "https://outlook.test") == 1


# ---------------------------------------------------------------------------
# thread / conversation command
# ---------------------------------------------------------------------------

def test_thread_lists_conversation(monkeypatch, capsys):
    seen = {}

    def fake_get(api_base, endpoint, token, **kwargs):
        seen["endpoint"] = endpoint
        return {"value": [{"Id": "m1", "Subject": "Re: hi", "ConversationId": "C1"}]}

    monkeypatch.setattr(cli.api_mod, "api_get", fake_get)
    assert cli.cmd_thread(["--id", "C1"], {}, "tok", "https://outlook.test") == 0
    assert seen["endpoint"].startswith("me/messages?")
    assert "ConversationId%20eq%20%27C1%27" in seen["endpoint"]
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["subject"] == "Re: hi"


def test_thread_positional_and_alias_flag(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: {"value": []})
    assert cli.cmd_thread(["C1", "--pretty"], {}, "tok", "https://outlook.test") == 0
    assert cli.cmd_thread(["--conversation", "C1"], {}, "tok", "https://outlook.test") == 0


def test_thread_all_pages(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, "paginate_all",
        lambda base, endpoint, token, **k: [{"Id": "m1", "Subject": "x", "ConversationId": "C1"}],
    )
    assert cli.cmd_thread(["--id", "C1", "--all"], {}, "tok", "https://outlook.test") == 0
    assert json.loads(capsys.readouterr().out)[0]["subject"] == "x"


def test_thread_requires_id_and_handles_failure(monkeypatch):
    with pytest.raises(cli.UsageError, match="--id is required"):
        cli.cmd_thread([], {}, "tok", "https://outlook.test")
    monkeypatch.setattr(cli.api_mod, "api_get", lambda *a, **k: None)
    assert cli.cmd_thread(["--id", "C1"], {}, "tok", "https://outlook.test") == 1


def test_conversation_filter_escapes():
    assert messages_mod.conversation_filter("a'b") == "ConversationId eq 'a''b'"
