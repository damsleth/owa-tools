# AGENTS.md

`owa_teams` reads Microsoft Teams across **two doors**, because no single token
covers both enumeration and message bodies under owa-piggy's FOCI client.

- **Enumeration uses the `graph` token.** `teams` (`/me/joinedTeams`, no
  `$select`/`$top` - Graph 400s those under delegated auth), `channels`
  (`/teams/{id}/channels`), and `chats` (`/me/chats`) all work on the plain
  Graph token. `auth.graph_setup` returns `(token, https://graph.microsoft.com/v1.0)`.
- **Message bodies use the `ic3` token against the chat service.** Graph's
  `/teams/.../messages` requires `ChannelMessage.Read.All`, which AADSTS65002
  blocks for this client (probed live: 403). The Teams web client reads bodies
  from `https://teams.microsoft.com/api/chatsvc/{region}/v1/users/ME/conversations/{id}/messages`
  with an `ic3`-audience bearer. Verified live 2026-06-02 (crayon/emea): 200 on
  every channel tested, no skypetoken/authsvc exchange needed. `auth.chatsvc_setup`
  returns `(token, https://teams.microsoft.com/api/chatsvc/{region}/v1)`.
- **Channel threading is keyed on top-level `rootMessageId`, NOT
  `properties.parentmessageid`** (which is null in practice). The chatsvc
  channel stream is flat - roots and replies interleaved, ordered by
  `sequenceId`. A message is a root when `rootMessageId` is absent/`"0"`/equal
  to its own `id`; only roots carry `properties.subject`. `teams.normalize_channel_messages`
  reconstructs every thread in one pass (`threadId = "{channel_id}:{root_id}"`,
  replies inherit the root's subject). Chats are genuinely flat (one chat = one
  thread) - `teams.normalize_chat_messages`. Do not "simplify" channels back
  onto `parentmessageid` or the Graph `/replies` endpoint - both are dead here.
- **Region** is part of the chatsvc path (`emea`/`amer`/`apac`/...). v1 pins it
  via `config.teams_region` (default `emea`). Proper resolution - the authsvc
  `regionGtms.chatService` round-trip on a spaces/teams token - is a later
  enhancement; until then, non-EU profiles must `owa-teams config --region`.
- The chatsvc stream pages via `_metadata.backwardLink` (absolute URL, older
  direction), NOT Graph's `@odata.nextLink`, so `api.chatsvc_messages` follows
  it itself rather than reusing `owa_core.http.paginate`. Graph collections do
  use the shared paginator (`api.graph_paginate`).
- **v1 is read-only.** Posting messages (chatsvc POST, destructive + confirm),
  team members (`/teams/{id}/members`, scope-gated - teaminal sidesteps it via
  message MRI + `imdisplayname`), and Teams meeting metadata (an onlineMeeting
  surface that belongs with owa-cal) are deferred.
- Command spec: `COMMAND_SCHEMA` in `cli.py`. Docs live in `docs/teams.md`.

Nearest tests: `src/tests/teams/`.

Verify:

```bash
.venv/bin/ruff check src/owa_teams src/tests/teams
.venv/bin/python -m pytest -q src/tests/teams
```
