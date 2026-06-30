# owa-teams

Microsoft Teams CLI for Microsoft 365. List your joined teams and their
channels, list your chats and their members, read **channel** and **chat
messages** — with channel replies threaded — and **send** or **reply** to
messages. Pipe-friendly JSON by default, `--pretty` for humans.

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
owa-teams config --region amer                       # pin the default
owa-teams messages --chat <id> --region amer         # override one read only
owa-teams --profile work teams
```

> Automatic region resolution (the authsvc `regionGtms` round-trip) is deferred;
> non-EU tenants should pin `--region` for now. `messages --region <region>`
> overrides the configured/default region for a single call — handy for
> multi-region profiles without rewriting `config.teams_region`.

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
owa-teams chats --top 20                                  # cap at 20 (default 50)
owa-teams channels --team <id> --all                      # fetch every page

owa-teams messages --channel "19:abc@thread.tacv2" --pretty       # channel posts + replies
owa-teams messages --channel "19:abc@thread.tacv2" --team <id> --limit 4
owa-teams messages --chat "19:def@unq.gbl.spaces"                 # a flat chat thread
owa-teams messages --channel "19:abc@thread.tacv2" --system-events  # include system events
owa-teams messages --chat "19:def@unq.gbl.spaces" --since 2026-06-01  # only since a date
owa-teams messages --chat "19:def@unq.gbl.spaces" --region amer       # override region

owa-teams members --chat "19:def@unq.gbl.spaces" --pretty         # chat members
owa-teams members --channel "19:abc@thread.tacv2" --team <id>     # channel members (walled)

owa-teams send --chat "19:def@unq.gbl.spaces" --text "hi there"   # send a chat message
owa-teams send --channel "19:abc@thread.tacv2" --text "new topic" --subject "Q3 plan"
owa-teams send --channel "19:abc@thread.tacv2" --reply-to 1665994613428 --text "agreed"
owa-teams send --chat "19:def@unq.gbl.spaces" --text "ping" --mention "8:orgid:<oid>=Ada"
owa-teams send --chat "19:def@unq.gbl.spaces" --html --text "<b>bold</b>"
owa-teams send --chat "19:def@unq.gbl.spaces" --text "see doc" --attachment "Spec=https://x/f"

owa-teams config --region amer                            # pin the chatsvc region
owa-teams config --profile work                           # pin a default profile
owa-teams refresh                                         # verify Graph access
```

`channels` requires `--team` (flag or bare positional). `messages`, `members`,
and `send` each require exactly one of `--channel` or `--chat`; for `messages`
`--team` is optional and echoed into each channel message's metadata, and for
`members --channel` it is required.

### Paging

`channels` and `chats` page Graph collections. `--top <n>` caps output at `n`
items (default 50) and stops following `@odata.nextLink` early; `--all` fetches
every page. When more items remain unfetched, a truncation note is written to
stderr (stdout stays valid JSON).

### Sending and replying

`send` posts to the regional chat service (the same `ic3` door `messages`
reads from — verified live: the `ic3` bearer carries `Endpoint.ReadWrite.All`
and the POST returns `201`). It is **mutating** and confirmation-gated: it
prompts on a TTY and refuses to run non-interactively without `--confirm`. Each
POST carries a generated `clientmessageid` idempotency key (the chat service
dedups on it), echoed back in the result:

```json
{"sent": true, "conversationId": "19:def@unq.gbl.spaces", "clientMessageId": "12876…", "originalArrivalTime": 1782782299302}
```

- `--text <msg>` is the message body; plain text is HTML-escaped. `--html`
  sends `--text` as a raw HTML body untouched.
- `--reply-to <root-id>` threads the post under a channel thread's root
  (`rootMessageId`); `--subject <text>` titles a *new* channel thread.
- `--mention "<mri[=Name]>"` (repeatable) adds an @-mention: each prepends an
  `<at id="N">` tag to the body and a structured entry to `properties.mentions`.
- `--attachment "<url>"` or `"<name=url>"` (repeatable) adds a link card.

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

- **Members.** `members --chat` works on the plain Graph token
  (`/chats/{id}/members`, 200). **Channel and team members are walled**: Graph's
  `/teams/{id}/channels/{id}/members` and `/teams/{id}/members` require
  `ChannelMember.Read.All` / `TeamMember.Read.All`, which owa-piggy's FOCI client
  cannot obtain (live probe 2026-06-30: `403`). `members --channel` is
  implemented against the documented endpoint but surfaces that `403` as a
  scope-insufficient error (exit `12`).
- **Sending is open.** Unlike channel *message reads* (which Graph walls and the
  chat service serves), the chat-service POST accepts the `ic3` bearer directly —
  no skypetoken/authsvc exchange. Channel replies set `rootMessageId` in the POST
  body; new channel threads carry a `subject`.
- Channel replies are **not** reachable on Graph (the `/replies` endpoint needs
  `ChannelMessage.Read.All`); they arrive in the flat chatsvc stream instead and
  are threaded via `rootMessageId`. Do not route channel reads back onto Graph.
- The chat service pages via `_metadata.backwardLink` (older direction), not
  Graph's `@odata.nextLink`; `--limit` bounds how many pages are fetched.
- Teams meeting metadata (an onlineMeeting surface that overlaps owa-cal) remains
  deferred.

See [`AGENTS.md`](../src/owa_teams/AGENTS.md) for repo layout and ground rules.
