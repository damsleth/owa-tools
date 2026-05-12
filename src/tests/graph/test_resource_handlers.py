"""Direct tests for curated owa-graph resource shortcut handlers."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from owa_core.errors import InternalError, UsageError
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


def test_calendar_mutations_and_validation(ctx):
    assert calendar.cmd_create(["--subject", "Sync", "--start", "9", "--end", "10", "--attendees", "a@x, b@x", "--body", "hi"], ctx) == 0
    assert ctx.calls[-1][0:2] == ("POST", "/me/events")
    assert ctx.calls[-1][2]["attendees"][1]["emailAddress"]["address"] == "b@x"
    assert ctx.calls[-1][2]["body"]["content"] == "hi"

    with pytest.raises(UsageError, match="create requires"):
        calendar.cmd_create([], ctx)

    assert calendar.cmd_update(["evt", "--subject", "New"], ctx) == 0
    assert ctx.calls[-1] == ("PATCH", "/me/events/evt", {"subject": "New"}, None, None)
    with pytest.raises(UsageError, match="update needs"):
        calendar.cmd_update(["--id", "evt"], ctx)

    assert calendar.cmd_delete(["evt"], ctx) == 0
    assert ctx.calls[-1] == ("DELETE", "/me/events/evt", None)
    assert calendar.cmd_findtimes(["--attendees", "a@x,b@x", "--duration", "PT1H"], ctx) == 0
    assert ctx.calls[-1][1] == "/me/findMeetingTimes"
    assert ctx.calls[-1][2]["meetingDuration"] == "PT1H"
    assert calendar.cmd_accept(["evt", "--comment", "ok"], ctx) == 0
    assert ctx.calls[-1] == ("POST", "/me/events/evt/accept", {"comment": "ok", "sendResponse": True}, None, None)
    with pytest.raises(UsageError, match="decline requires"):
        calendar.cmd_decline([], ctx)


def test_chats_handlers(ctx):
    assert chats.cmd_list(["--top", "3"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/me/chats", [("$top", "3")], None, None, False)
    assert chats.cmd_messages(["chat-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/chats/chat-1/messages"
    with pytest.raises(UsageError, match="messages requires"):
        chats.cmd_messages([], ctx)
    assert chats.cmd_send(["--chat", "chat-1", "--body", "hello"], ctx) == 0
    assert ctx.calls[-1] == ("POST", "/chats/chat-1/messages", {"body": {"content": "hello"}}, None, None)
    with pytest.raises(UsageError):
        chats.cmd_send([], ctx)


def test_contacts_handlers(ctx):
    assert contacts.cmd_list(["--top", "2"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/me/contacts", [("$top", "2")], None, None, False)
    assert contacts.cmd_find(["ada"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/me/contacts", [("$search", '"ada"')], {"ConsistencyLevel": "eventual"}, None, False)
    with pytest.raises(UsageError, match="find requires"):
        contacts.cmd_find([], ctx)
    assert contacts.cmd_create(["--name", "Ada", "--email", "ada@example.com"], ctx) == 0
    assert ctx.calls[-1][2]["emailAddresses"] == [{"address": "ada@example.com", "name": "Ada"}]
    with pytest.raises(UsageError):
        contacts.cmd_create([], ctx)
    assert contacts.cmd_delete(["person-1"], ctx) == 0
    assert ctx.calls[-1] == ("DELETE", "/me/contacts/person-1", None)
    with pytest.raises(UsageError):
        contacts.cmd_delete([], ctx)


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

    with pytest.raises(UsageError, match="download requires"):
        files.cmd_download([], ctx)

    monkeypatch.setattr(files.api_mod, "api_request", lambda *args, **kwargs: b"abc")
    assert files.cmd_download(["--id", "item-1"], ctx) == 0
    assert capfd.readouterr().out == "abc"

    src = tmp_path / "upload.txt"
    src.write_text("content", encoding="utf-8")
    assert files.cmd_upload(["--file", str(src), "--path", "/upload.txt"], ctx) == 0
    assert ctx.calls[-1][0:2] == ("PUT", "/me/drive/root:/upload.txt:/content")
    assert ctx.calls[-1][3] == {"Content-Type": "application/octet-stream"}
    with pytest.raises(UsageError, match="not a file"):
        files.cmd_upload(["--file", str(tmp_path / "missing"), "--path", "/x"], ctx)

    assert files.cmd_share(["item-1", "--type", "edit", "--scope", "anonymous"], ctx) == 0
    assert ctx.calls[-1] == ("POST", "/me/drive/items/item-1/createLink", {"type": "edit", "scope": "anonymous"}, None, None)
    assert files.cmd_delete(["item-1"], ctx) == 0
    assert ctx.calls[-1] == ("DELETE", "/me/drive/items/item-1", None)
    assert files.cmd_search(["budget", "--top", "4"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/me/drive/root/search(q='budget')", [("$top", "4")], None, "drive", False)
    with pytest.raises(UsageError):
        files.cmd_search([], ctx)


def test_groups_handlers(ctx):
    assert groups.cmd_list(["--top", "8", "--filter", "startswith(displayName,'A')"], ctx) == 0
    assert ctx.calls[-1][1] == "/groups"
    assert ctx.calls[-1][2][-1] == ("$filter", "startswith(displayName,'A')")
    assert groups.cmd_members(["group-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/groups/group-1/members"
    with pytest.raises(UsageError, match="members requires"):
        groups.cmd_members([], ctx)
    assert groups.cmd_add(["--id", "group-1", "--user", "user-1"], ctx) == 0
    assert ctx.calls[-1][2] == {"@odata.id": "https://graph.microsoft.com/v1.0/directoryObjects/user-1"}
    assert groups.cmd_remove(["--id", "group-1", "--user", "user-1"], ctx) == 0
    assert ctx.calls[-1] == ("DELETE", "/groups/group-1/members/user-1/$ref", None)
    with pytest.raises(UsageError):
        groups.cmd_remove(["--id", "group-1"], ctx)


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


def test_planner_handlers(ctx, monkeypatch):
    assert planner.cmd_tasks([], ctx) == 0
    assert ctx.calls[-1][1] == "/me/planner/tasks"
    assert planner.cmd_plans([], ctx) == 0
    assert ctx.calls[-1][1] == "/me/planner/plans"
    assert planner.cmd_buckets(["plan-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/planner/plans/plan-1/buckets"
    with pytest.raises(UsageError, match="buckets requires"):
        planner.cmd_buckets([], ctx)

    monkeypatch.setattr(graph_api, "api_request", lambda *args, **kwargs: {"@odata.etag": "tag-1"})
    assert planner.cmd_complete(["task-1"], ctx) == 0
    assert ctx.calls[-1] == ("PATCH", "/planner/tasks/task-1", {"percentComplete": 100}, {"If-Match": "tag-1"}, None)

    monkeypatch.setattr(graph_api, "api_request", lambda *args, **kwargs: {"id": "task-1"})
    with pytest.raises(InternalError, match="no etag"):
        planner.cmd_complete(["task-1"], ctx)
    monkeypatch.setattr(graph_api, "api_request", lambda *args, **kwargs: None)
    assert planner.cmd_complete(["task-1"], ctx) == 1
    with pytest.raises(UsageError):
        planner.cmd_complete([], ctx)


def test_presence_handlers(ctx):
    assert presence.cmd_me([], ctx) == 0
    assert ctx.calls[-1][1] == "/me/presence"
    assert presence.cmd_get(["user-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/users/user-1/presence"
    with pytest.raises(UsageError, match="get requires"):
        presence.cmd_get([], ctx)
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
    with pytest.raises(UsageError):
        presence.cmd_set([], ctx)


def test_sites_handlers(ctx):
    assert sites.cmd_find(["sharepoint"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/sites", [("search", "sharepoint")], None, None, False)
    with pytest.raises(UsageError, match="find requires"):
        sites.cmd_find([], ctx)
    assert sites.cmd_lists(["site-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/sites/site-1/lists"
    with pytest.raises(UsageError):
        sites.cmd_lists([], ctx)
    assert sites.cmd_items(["site-1", "list-1", "--top", "6"], ctx) == 0
    assert ctx.calls[-1] == (
        "GET",
        "/sites/site-1/lists/list-1/items",
        [("$top", "6"), ("$expand", "fields")],
        None,
        None,
        False,
    )
    with pytest.raises(UsageError):
        sites.cmd_items(["site-1"], ctx)


def test_teams_handlers(ctx):
    assert teams.cmd_joined([], ctx) == 0
    assert ctx.calls[-1][1] == "/me/joinedTeams"
    assert teams.cmd_channels(["team-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/teams/team-1/channels"
    with pytest.raises(UsageError, match="channels requires"):
        teams.cmd_channels([], ctx)
    assert teams.cmd_messages(["team-1", "chan-1", "--top", "2"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/teams/team-1/channels/chan-1/messages", [("$top", "2")], None, None, False)
    assert teams.cmd_send(["--team", "team-1", "--channel", "chan-1", "--body", "hello"], ctx) == 0
    assert ctx.calls[-1][1] == "/teams/team-1/channels/chan-1/messages"
    assert teams.cmd_members(["team-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/teams/team-1/members"
    with pytest.raises(UsageError):
        teams.cmd_members([], ctx)


def test_todo_handlers(ctx):
    assert todo.cmd_lists([], ctx) == 0
    assert ctx.calls[-1][1] == "/me/todo/lists"
    assert todo.cmd_tasks(["list-1", "--top", "3"], ctx) == 0
    assert ctx.calls[-1] == ("GET", "/me/todo/lists/list-1/tasks", [("$top", "3")], None, None, False)
    with pytest.raises(UsageError, match="tasks requires"):
        todo.cmd_tasks([], ctx)
    assert todo.cmd_add(["--list", "list-1", "--title", "Ship", "--body", "details"], ctx) == 0
    assert ctx.calls[-1][2] == {"title": "Ship", "body": {"contentType": "text", "content": "details"}}
    with pytest.raises(UsageError):
        todo.cmd_add(["--list", "list-1"], ctx)
    assert todo.cmd_complete(["--list", "list-1", "--id", "task-1"], ctx) == 0
    assert ctx.calls[-1] == ("PATCH", "/me/todo/lists/list-1/tasks/task-1", {"status": "completed"}, None, None)
    with pytest.raises(UsageError):
        todo.cmd_complete(["--list", "list-1"], ctx)


def test_users_handlers(ctx):
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
    with pytest.raises(UsageError, match="find requires"):
        users.cmd_find([], ctx)
    assert users.cmd_get(["user-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/users/user-1"
    assert users.cmd_manager(["user-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/users/user-1/manager"
    assert users.cmd_directreports(["user-1"], ctx) == 0
    assert ctx.calls[-1][1] == "/users/user-1/directReports"
    with pytest.raises(UsageError):
        users.cmd_directreports([], ctx)


def test_mail_resource_remaining_handlers(ctx):
    from owa_graph.resources import mail

    assert mail.cmd_read(["m1"], ctx) == 0
    assert ctx.calls[-1][1] == "/me/messages/m1"
    with pytest.raises(UsageError, match="read requires"):
        mail.cmd_read([], ctx)

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
    with pytest.raises(UsageError, match="forward requires"):
        mail.cmd_forward(["m1"], ctx)

    assert mail.cmd_move(["m1", "--to", "Archive"], ctx) == 0
    assert ctx.calls[-1] == ("POST", "/me/messages/m1/move", {"destinationId": "Archive"}, None, None)
    with pytest.raises(UsageError):
        mail.cmd_move(["m1"], ctx)
    assert mail.cmd_flag(["m1", "--status", "complete"], ctx) == 0
    assert ctx.calls[-1] == ("PATCH", "/me/messages/m1", {"flag": {"flagStatus": "complete"}}, None, None)
