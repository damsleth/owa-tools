# owa-teams

Microsoft Teams CLI for Microsoft 365. List your joined teams and their
channels, list your chats, and read **channel** and **chat messages** — with
channel replies threaded. Pipe-friendly JSON by default, `--pretty` for humans.
**Read-only** in this version.

```sh
brew install damsleth/tap/owa-tools
owa-teams teams --pretty
```

`owa-teams` is part of the `owa-tools` suite and shares the `owa-piggy` auth
broker. You can also reach it through the umbrella: `owa teams channels --team
<id>` is identical to `owa-teams channels --team <id>`.

---

## Auth and scope — the two doors

owa-teams reads two surfaces, each behind its own owa-piggy audience:

1. **Enumeration** (`teams`, `channels`, `chats`) rides the plain **`graph`**
   token the One Outlook Web client already carries (`/me/joinedTeams`,
   `/teams/{id}/channels`, `/me/chats`).
2. **Message bodies** (`messages`) come from the **regional chat service**, not
   Graph. Graph's `/teams/.../messages` requires `ChannelMessage.Read.All`,
   which the broker's FOCI client cannot obtain (`AADSTS65002`) — so the channel
   message door on Graph is a hard `403`. The Teams web client reads bodies from
   `https://teams.microsoft.com/api/chatsvc/{region}/v1/...` with an **`ic3`**
   audience token, and that door is open. owa-teams mints both tokens for you.

The chat service is regional. The region is a short segment in the path
(`emea`/`amer`/`apac`/`ind`/...); it defaults to `emea`. Pin another:

```sh
owa-teams config --region amer
owa-teams --profile work teams
```

> Automatic region resolution (the authsvc `regionGtms` round-trip) is deferred;
> non-EU tenants should pin `--region` for now.

---

## Channel threading

A Teams channel is one chat-service conversation that holds **many** threads.
The message stream is flat — root posts and their replies are interleaved and
ordered by a monotonic `sequenceId` — and the thread key is the top-level
**`rootMessageId`** (not `properties.parentmessageid`, which is null in
practice). owa-teams reconstructs threads in a single pass:

- a message is a **root** when `rootMessageId` equals its own `id`; only roots
  carry a `subject`;
- a **reply** has a different `rootMessageId` and inherits its root's `subject`;
- every message is tagged `threadId = "{channelId}:{rootId}"`, so a consumer can
  group a root with its replies without a second call.

Chats (`--chat`) have no root/reply structure: one chat is one thread.

---

## The output contract

**JSON on stdout, logs on stderr.** HTML bodies are stripped to text; the wire
shape is stable lowercase keys, so it composes with `jq`:

```sh
owa-teams channels --team <team-id> | jq '.[] | select(.membershipType=="standard") | .displayName'
owa-teams messages --channel "19:abc@thread.tacv2" | jq 'group_by(.threadId) | map({thread: .[0].subject, count: length})'
```

A channel message normalizes to:

```json
[
  {
    "id": "1667290632494",
    "threadId": "19:abc@thread.tacv2:1665994613428",
    "rootMessageId": "1665994613428",
    "isReply": true,
    "sequenceId": 11,
    "from": {"id": "oid-redacted", "name": "Line", "mri": "8:orgid:oid-redacted"},
    "timestamp": "2022-11-01T08:17:12.494Z",
    "subject": "TV-aksjonen 2022",
    "content": "Herlige nyheter!",
    "messageType": "RichText/Html",
    "teamId": "team-guid",
    "channelId": "19:abc@thread.tacv2"
  }
]
```

System events and empty bodies are dropped by default; pass `--all` to keep
them. Messages are returned oldest-first; the chat service is paged backward via
its `backwardLink` cursor, bounded by `--limit` pages. `--since <iso>` adds a
time floor: paging stops as soon as a page reaches past the cutoff (no point
following `backwardLink` into strictly older pages), and the result is trimmed to
messages at/after that time. Messages with no parseable timestamp are kept.

---

## Commands

```sh
owa-teams teams --pretty                                  # my joined teams (alias: ls)
owa-teams ls                                              # same thing

owa-teams channels --team 3360397c-8ad3-499e-8d71-a83856c0f252 --pretty
owa-teams channels 3360397c-8ad3-499e-8d71-a83856c0f252   # team id as a positional

owa-teams chats --pretty                                  # my chats
owa-teams chats --type meeting                            # only meeting chats

owa-teams messages --channel "19:abc@thread.tacv2" --pretty       # channel posts + replies
owa-teams messages --channel "19:abc@thread.tacv2" --team <id> --limit 4
owa-teams messages --chat "19:def@unq.gbl.spaces"                 # a flat chat thread
owa-teams messages --channel "19:abc@thread.tacv2" --all          # include system events
owa-teams messages --chat "19:def@unq.gbl.spaces" --since 2026-06-01  # only since a date

owa-teams config --region amer                            # pin the chatsvc region
owa-teams config --profile work                           # pin a default profile
owa-teams refresh                                         # verify Graph access
```

`channels` requires `--team` (flag or bare positional). `messages` requires
exactly one of `--channel` or `--chat`; `--team` is optional and is echoed into
each channel message's metadata.

---

## Machine / agent surface

Every owa binary exposes the same machine surface (see
[agent-integration.md](agent-integration.md) for the full contract):

- `owa-teams schema [<command>]` - JSON command schema (one command if named)
- `owa-teams --help --json` - the same schema via the help flag
- `--agent` - wrap JSON stdout in a stable `{"_owa": ..., "data": ...}` envelope
  (or set `OWA_AGENT=1`)
- `--err-json` - structured JSON errors on stderr (or `OWA_ERR_JSON=1`)
- `--doctor [--json]` - this tool's health / redaction doctor payload

---

## Notes

- **Read-only.** Posting a channel/chat message (chatsvc POST, destructive +
  confirmation-gated), team members, and Teams meeting metadata (an
  onlineMeeting surface that overlaps owa-cal) are deferred to a later phase.
- Channel replies are **not** reachable on Graph (the `/replies` endpoint needs
  `ChannelMessage.Read.All`); they arrive in the flat chatsvc stream instead and
  are threaded via `rootMessageId`. Do not route channel reads back onto Graph.
- The chat service pages via `_metadata.backwardLink` (older direction), not
  Graph's `@odata.nextLink`; `--limit` bounds how many pages are fetched.

See [`AGENTS.md`](../src/owa_teams/AGENTS.md) for repo layout and ground rules.
