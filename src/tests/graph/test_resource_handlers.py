"""Direct tests for curated owa-graph resource shortcut handlers."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from owa_graph import api as graph_api
from owa_graph.resources import (
    calendar,
    chats,
    contacts,
    directory,
    files,
    groups,
    me,
    planner,
    presence,
    sites,
    teams,
    todo,
    users,
)


@dataclass
class FakeCtx:
    api_base: str = "https://graph.microsoft.com/v1.0"
    access_token: str = "tok"
    debug: bool = False
    retry: bool = False
    calls: list[tuple] = field(default_factory=list)

    def get(self, path, *, query=None, headers=None, pretty_shape=None, paginate=False):
        self.calls.append(("GET", path, query, headers, pretty_shape, paginate))
        return 0

    def post(self, path, body, *, headers=None, pretty_shape=None):
        self.calls.append(("POST", path, body, headers, pretty_shape))
        return 0

    def patch(self, path, body, *, headers=None, pretty_shape=None):
        self.calls.append(("PATCH", path, body, headers, pretty_shape))
        return 0

    def put(self, path, body, *, headers=None, pretty_shape=None):
        self.calls.append(("PUT", path, body, headers, pretty_shape))
        return 0

    def delete(self, path, *, headers=None):
        self.calls.append(("DELETE", path, headers))
        return 0


@pytest.fixture
def ctx():
    return FakeCtx()


def test_calendar_events_defaults_and_view(ctx):
    assert calendar.cmd_events([], ctx) == 0
    assert ctx.calls[-1] == (
        "GET",
        "/me/events",
        [("$top", "25"), ("$orderby", "start/dateTime")],
        None,
        None,
        False,
    )

    assert calendar.cmd_events(
        ["--from", "2026-05-09T09:00:00", "--to", "2026-05-09T17:00:00", "--top", "5", "--select", "id"],
        ctx,
    ) == 0
    assert ctx.calls[-1] == (
        "GET",
        "/me/calendarView",
        [
            ("startDateTime", "2026-05-09T09:00:00"),
            ("endDateTime", "2026-05-09T17:00:00"),
            ("$top", "5"),
            ("$select", "id"),
        ],
        None,
        None,
        False,
    )


def test_calendar_mutations_and_validation(ctx, capsys):
    assert calendar.cmd_create(["--subject", "Sync", "--start", "9", "--end", "10", "--attendees", "a@x, b@x", "--body", "hi"], ctx) == 0
    assert ctx.calls[-1][0:2] == ("POST", "/me/events")
    assert ctx.calls[-1][2]["attendees"][1]["emailAddress"]["address"] == "b@x"
    assert ctx.calls[-1][2]["body"]["content"] == "hi"

    assert calendar.cmd_create([], ctx) == 1
    assert "create requires" in capsys.readouterr().out

    assert calendar.cmd_update(["evt", "--subject", "New"], ctx) == 0
    assert ctx.calls[-1] == ("PATCH", "/me/events/evt", {"subject": "New"}, None, None)
    assert calendar.cmd_update(["--id", "evt"], ctx) == 1
    assert "update needs" in capsys.readouterr().out

    assert calendar.cmd_delete(["evt"], ctx) == 0
    assert ctx.calls[-1] == ("DELETE", "/me/events/evt", None)
    assert calendar.cmd_findtimes(["--attendees", "a@x,b@x", "--duration", "PT1H"], ctx) == 0
    assert ctx.calls[-1][1] == "/me/findMeetingTimes"
    assert ctx.calls[-1][2]["meetingDuration"] == "PT1H"
    assert calendar.cmd_accept(["evt", "--comment", "ok"], ctx) == 0
    assert ctx.calls[-1] == ("POST", "/me/events/evt/accept", {"comment": "ok", "sendResponse": True}, None, None)
    assert calendar.cmd_decline([], ctx) == 1
    assert "decline requires" in capsys.readouterr().out


def test_chats_handlers(ctx, capsys):
    assert chats.cmd_list(["--top", "3"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/me/chats", [("$top", "3")], None, None, False)
    assert chats.cmd_messages(["chat-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/chats/chat-1/messages"
    assert chats.cmd_messages([], ctx) == 1
    assert "messages requires" in capsys.readouterr().out
    assert chats.cmd_send(["--chat", "chat-1", "--body", "hello"], ctx) == 0
    assert ctx.calls[-1] == ("POST", "/chats/chat-1/messages", {"body": {"content": "hello"}}, None, None)
    assert chats.cmd_send([], ctx) == 1


def test_contacts_handlers(ctx, capsys):
    assert contacts.cmd_list(["--top", "2"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/me/contacts", [("$top", "2")], None, None, False)
    assert contacts.cmd_find(["ada"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/me/contacts", [("$search", '"ada"')], {"ConsistencyLevel": "eventual"}, None, False)
    assert contacts.cmd_find([], ctx) == 1
    assert "find requires" in capsys.readouterr().out
    assert contacts.cmd_create(["--name", "Ada", "--email", "ada@example.com"], ctx) == 0
    assert ctx.calls[-1][2]["emailAddresses"] == [{"address": "ada@example.com", "name": "Ada"}]
    assert contacts.cmd_create([], ctx) == 1
    assert contacts.cmd_delete(["person-1"], ctx) == 0
    assert ctx.calls[-1] == ("DELETE", "/me/contacts/person-1", None)
    assert contacts.cmd_delete([], ctx) == 1


def test_directory_handlers(ctx):
    assert directory.cmd_roles([], ctx) == 0
    assert ctx.calls[-1][1] == "/directoryRoles"
    assert directory.cmd_auditlogs(["--top", "7", "--filter", "activityDateTime ge now"], ctx) == 0
    assert ctx.calls[-1] == (
        "GET",
        "/auditLogs/directoryAudits",
        [("$top", "7"), ("$filter", "activityDateTime ge now")],
        None,
        None,
        False,
    )


def test_files_handlers(ctx, tmp_path, monkeypatch, capfd):
    assert files.cmd_list(["--path", "/Reports", "--top", "9"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/me/drive/root:/Reports:/children", [("$top", "9")], None, "drive", False)

    assert files.cmd_download([], ctx) == 1
    assert "download requires" in capfd.readouterr().out

    monkeypatch.setattr(files.api_mod, "api_request", lambda *args, **kwargs: b"abc")
    assert files.cmd_download(["--id", "item-1"], ctx) == 0
    assert capfd.readouterr().out == "abc"

    src = tmp_path / "upload.txt"
    src.write_text("content", encoding="utf-8")
    assert files.cmd_upload(["--file", str(src), "--path", "/upload.txt"], ctx) == 0
    assert ctx.calls[-1][0:2] == ("PUT", "/me/drive/root:/upload.txt:/content")
    assert ctx.calls[-1][3] == {"Content-Type": "application/octet-stream"}
    assert files.cmd_upload(["--file", str(tmp_path / "missing"), "--path", "/x"], ctx) == 1
    assert "not a file" in capfd.readouterr().out

    assert files.cmd_share(["item-1", "--type", "edit", "--scope", "anonymous"], ctx) == 0
    assert ctx.calls[-1] == ("POST", "/me/drive/items/item-1/createLink", {"type": "edit", "scope": "anonymous"}, None, None)
    assert files.cmd_delete(["item-1"], ctx) == 0
    assert ctx.calls[-1] == ("DELETE", "/me/drive/items/item-1", None)
    assert files.cmd_search(["budget", "--top", "4"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/me/drive/root/search(q='budget')", [("$top", "4")], None, "drive", False)
    assert files.cmd_search([], ctx) == 1


def test_groups_handlers(ctx, capsys):
    assert groups.cmd_list(["--top", "8", "--filter", "startswith(displayName,'A')"], ctx) == 0
    assert ctx.calls[-1][1] == "/groups"
    assert ctx.calls[-1][2][-1] == ("$filter", "startswith(displayName,'A')")
    assert groups.cmd_members(["group-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/groups/group-1/members"
    assert groups.cmd_members([], ctx) == 1
    assert "members requires" in capsys.readouterr().out
    assert groups.cmd_add(["--id", "group-1", "--user", "user-1"], ctx) == 0
    assert ctx.calls[-1][2] == {"@odata.id": "https://graph.microsoft.com/v1.0/directoryObjects/user-1"}
    assert groups.cmd_remove(["--id", "group-1", "--user", "user-1"], ctx) == 0
    assert ctx.calls[-1] == ("DELETE", "/groups/group-1/members/user-1/$ref", None)
    assert groups.cmd_remove(["--id", "group-1"], ctx) == 1


def test_me_handlers(ctx, monkeypatch, capfd):
    assert me.cmd_whoami([], ctx) == 0
    assert ctx.calls[-1][1] == "/me"
    assert me.cmd_manager([], ctx) == 0
    assert ctx.calls[-1][1] == "/me/manager"
    assert me.cmd_directreports([], ctx) == 0
    assert ctx.calls[-1][1] == "/me/directReports"
    monkeypatch.setattr(graph_api, "api_request", lambda *args, **kwargs: b"photo")
    assert me.cmd_photo([], ctx) == 0
    assert capfd.readouterr().out == "photo"
    monkeypatch.setattr(graph_api, "api_request", lambda *args, **kwargs: None)
    assert me.cmd_photo([], ctx) == 1


def test_planner_handlers(ctx, monkeypatch, capsys):
    assert planner.cmd_tasks([], ctx) == 0
    assert ctx.calls[-1][1] == "/me/planner/tasks"
    assert planner.cmd_plans([], ctx) == 0
    assert ctx.calls[-1][1] == "/me/planner/plans"
    assert planner.cmd_buckets(["plan-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/planner/plans/plan-1/buckets"
    assert planner.cmd_buckets([], ctx) == 1
    assert "buckets requires" in capsys.readouterr().out

    monkeypatch.setattr(graph_api, "api_request", lambda *args, **kwargs: {"@odata.etag": "tag-1"})
    assert planner.cmd_complete(["task-1"], ctx) == 0
    assert ctx.calls[-1] == ("PATCH", "/planner/tasks/task-1", {"percentComplete": 100}, {"If-Match": "tag-1"}, None)

    monkeypatch.setattr(graph_api, "api_request", lambda *args, **kwargs: {"id": "task-1"})
    assert planner.cmd_complete(["task-1"], ctx) == 1
    assert "no etag" in capsys.readouterr().out
    monkeypatch.setattr(graph_api, "api_request", lambda *args, **kwargs: None)
    assert planner.cmd_complete(["task-1"], ctx) == 1
    assert planner.cmd_complete([], ctx) == 1


def test_presence_handlers(ctx, capsys):
    assert presence.cmd_me([], ctx) == 0
    assert ctx.calls[-1][1] == "/me/presence"
    assert presence.cmd_get(["user-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/users/user-1/presence"
    assert presence.cmd_get([], ctx) == 1
    assert "get requires" in capsys.readouterr().out
    assert presence.cmd_set(["--availability", "Busy", "--activity", "InACall", "--duration", "PT1H", "--app", "app-1"], ctx) == 0
    assert ctx.calls[-1] == (
        "POST",
        "/me/presence/setPresence",
        {
            "sessionId": "app-1",
            "availability": "Busy",
            "activity": "InACall",
            "expirationDuration": "PT1H",
        },
        None,
        None,
    )
    assert presence.cmd_set([] , ctx) == 1


def test_sites_handlers(ctx, capsys):
    assert sites.cmd_find(["sharepoint"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/sites", [("search", "sharepoint")], None, None, False)
    assert sites.cmd_find([], ctx) == 1
    assert "find requires" in capsys.readouterr().out
    assert sites.cmd_lists(["site-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/sites/site-1/lists"
    assert sites.cmd_lists([], ctx) == 1
    assert sites.cmd_items(["site-1", "list-1", "--top", "6"], ctx) == 0
    assert ctx.calls[-1] == (
        "GET",
        "/sites/site-1/lists/list-1/items",
        [("$top", "6"), ("$expand", "fields")],
        None,
        None,
        False,
    )
    assert sites.cmd_items(["site-1"], ctx) == 1


def test_teams_handlers(ctx, capsys):
    assert teams.cmd_joined([], ctx) == 0
    assert ctx.calls[-1][1] == "/me/joinedTeams"
    assert teams.cmd_channels(["team-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/teams/team-1/channels"
    assert teams.cmd_channels([], ctx) == 1
    assert "channels requires" in capsys.readouterr().out
    assert teams.cmd_messages(["team-1", "chan-1", "--top", "2"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/teams/team-1/channels/chan-1/messages", [("$top", "2")], None, None, False)
    assert teams.cmd_send(["--team", "team-1", "--channel", "chan-1", "--body", "hello"], ctx) == 0
    assert ctx.calls[-1][1] == "/teams/team-1/channels/chan-1/messages"
    assert teams.cmd_members(["team-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/teams/team-1/members"
    assert teams.cmd_members([], ctx) == 1


def test_todo_handlers(ctx, capsys):
    assert todo.cmd_lists([], ctx) == 0
    assert ctx.calls[-1][1] == "/me/todo/lists"
    assert todo.cmd_tasks(["list-1", "--top", "3"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/me/todo/lists/list-1/tasks", [("$top", "3")], None, None, False)
    assert todo.cmd_tasks([], ctx) == 1
    assert "tasks requires" in capsys.readouterr().out
    assert todo.cmd_add(["--list", "list-1", "--title", "Ship", "--body", "details"], ctx) == 0
    assert ctx.calls[-1][2] == {"title": "Ship", "body": {"contentType": "text", "content": "details"}}
    assert todo.cmd_add(["--list", "list-1"], ctx) == 1
    assert todo.cmd_complete(["--list", "list-1", "--id", "task-1"], ctx) == 0
    assert ctx.calls[-1] == ("PATCH", "/me/todo/lists/list-1/tasks/task-1", {"status": "completed"}, None, None)
    assert todo.cmd_complete(["--list", "list-1"], ctx) == 1


def test_users_handlers(ctx, capsys):
    assert users.cmd_list(["--top", "4", "--select", "id,mail", "--filter", "accountEnabled eq true"], ctx) == 0
    assert ctx.calls[-1] == (
        "GET",
        "/users",
        [("$top", "4"), ("$select", "id,mail"), ("$filter", "accountEnabled eq true")],
        None,
        "users",
        False,
    )
    assert users.cmd_find(["ada", "--top", "2"], ctx) == 0
    assert ctx.calls[-1] == (
        "GET",
        "/users",
        [("$search", '"displayName:ada" OR "mail:ada"'), ("$top", "2")],
        {"ConsistencyLevel": "eventual"},
        "users",
        False,
    )
    assert users.cmd_find([], ctx) == 1
    assert "find requires" in capsys.readouterr().out
    assert users.cmd_get(["user-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/users/user-1"
    assert users.cmd_manager(["user-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/users/user-1/manager"
    assert users.cmd_directreports(["user-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/users/user-1/directReports"
    assert users.cmd_directreports([], ctx) == 1


def test_mail_resource_remaining_handlers(ctx, capsys):
    from owa_graph.resources import mail

    assert mail.cmd_read(["m1"], ctx) == 0
    assert ctx.calls[-1][1] == "/me/messages/m1"
    assert mail.cmd_read([], ctx) == 1
    assert "read requires" in capsys.readouterr().out

    assert mail.cmd_reply(["m1", "--comment", "thanks"], ctx) == 0
    assert ctx.calls[-1] == ("POST", "/me/messages/m1/reply", {"comment": "thanks"}, None, None)
    assert mail.cmd_replyall(["m1"], ctx) == 0
    assert ctx.calls[-1][1] == "/me/messages/m1/replyAll"
    assert mail.cmd_forward(["m1", "--to", "a@example.com,b@example.com", "--comment", "fyi"], ctx) == 0
    assert ctx.calls[-1][1] == "/me/messages/m1/forward"
    assert [r["emailAddress"]["address"] for r in ctx.calls[-1][2]["toRecipients"]] == [
        "a@example.com",
        "b@example.com",
    ]
    assert mail.cmd_forward(["m1"], ctx) == 1
    assert "forward requires" in capsys.readouterr().out

    assert mail.cmd_move(["m1", "--to", "Archive"], ctx) == 0
    assert ctx.calls[-1] == ("POST", "/me/messages/m1/move", {"destinationId": "Archive"}, None, None)
    assert mail.cmd_move(["m1"], ctx) == 1
    assert mail.cmd_flag(["m1", "--status", "complete"], ctx) == 0
    assert ctx.calls[-1] == ("PATCH", "/me/messages/m1", {"flag": {"flagStatus": "complete"}}, None, None)
