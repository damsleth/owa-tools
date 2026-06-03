# owa-teams

> **Status: SHIPPED** — Phase 1 landed in **v0.7.0** (`eadbfb8`, 2026-06-02,
> `feat(owa-teams): add Microsoft Teams consumer CLI (read-only)`), plus the
> 429 Retry-After ride-through (`7d076fe`, 2026-06-03). Remaining nice-to-haves
> (`messages --since`, `messages --region`) are tracked as todos in
> [../TODO.md](../TODO.md). See [../DONE.md](../DONE.md).

_Created 2026-06-02_

A consumer binary for Microsoft Teams artefacts: **teams, channels, chats,
messages, and meetings**. First-class verbs over a surface that today only
exists as generic `owa-graph GET` calls + the type-sniffing formatters in
`owa_graph/format.py` (`_format_teams` / `_format_channels`).

## Why a dedicated tool (vs. "folded into owa-graph")

The 2026-06-01 note [[owa-piggy-token-scope-limits]] folded Teams *listing* into
owa-graph because `/me/joinedTeams` + `/teams/{id}/channels` already work with the
plain `graph` token. This tool earns its own binary for two reasons, mirroring
how `owa-planner` wraps Graph `/planner` and `owa-sites` wraps SharePoint REST:

1. **Ergonomics** — `owa-teams ls`, `channels`, `chats`, `messages`, `meetings`
   instead of memorising Graph paths and `--audience` flags.
2. **Dual-door auth** — message *bodies* (channel + chat) are the artefacts the
   plain `graph` token most likely can't read (`ChannelMessage.Read.All` /
   `Chat.Read` are not in the One Outlook Web client's fixed scope set). The Teams
   web client reads them via the chat service on the **`teams` audience**
   (`https://api.spaces.skype.com`) that owa-graph already knows. owa-teams is the
   natural home for that fallback door + its normalizers.

## Feasibility — VERDICT: PROBE-FIRST (each artefact is a separate scope gate)

Governing model unchanged: owa-piggy is pinned to client `9199bf20`; an artefact
is reachable only if that client preauthorizes the resource and the token carries
the delegated scope. **Phase 0 is a probe matrix — do not build a subcommand
until its door is confirmed green.** Expected priors (confirm live before coding):

| Artefact | Graph endpoint | Likely scope | Prior |
|---|---|---|---|
| Teams (joined) | `GET /me/joinedTeams` | `Team.ReadBasic.All` | **GREEN** (works today) |
| All teams | `GET /teams` | `Team.ReadBasic.All` | probe |
| Channels | `GET /teams/{id}/channels` | `Channel.ReadBasic.All` | **GREEN** (formatter exists) |
| Channel messages | `GET /teams/{id}/channels/{id}/messages` | `ChannelMessage.Read.All` | **likely RED** on Graph → try `teams` aud |
| My chats | `GET /me/chats` | `Chat.Read` | probe |
| Chat messages | `GET /chats/{id}/messages` | `Chat.Read` | probe → `teams` aud fallback |
| Online meetings | `GET /me/onlineMeetings?$filter=...` | `OnlineMeetings.Read` | probe (often RED for delegated) |
| Members | `GET /teams/{id}/members` | `TeamMember.Read.All` | probe |

Calendar-style "meetings" (the events) are already owa-cal's job — `meetings`
here means Teams *onlineMeeting* objects (join URL, organizer, recordings/
transcripts metadata), not calendar events. If `/me/onlineMeetings` is RED,
degrade `meetings` to "Teams events from the calendar" via a thin owa-cal reuse,
or drop it — decide in Phase 0.

## Phase 0 — probe matrix (the one gating step)

- [ ] For each row above, run `owa-graph GET <path>` (graph aud) and record
      200 / 401 / 403. For any RED row, retry on `--audience teams`
      (`https://api.spaces.skype.com`) and capture what 200s.
- [ ] Confirm the `teams`-audience base path shape for messages (the skype/chat
      service is NOT `/v1.0/...` Graph — capture the real path from Teams web
      devtools if Graph messages are walled).
- [ ] Write the green/red verdict back into this file before scaffolding. Build
      only the green verbs; document red ones as "walled (scope), see probe".

## Phase 0 findings — pre-resolved from teaminal (2026-06-02)

`~/code/teaminal` (Bun/TS Teams client, same FOCI/owa-piggy auth path) has already
probed most of this matrix live. Verdict, with the one correction the priors miss:

| Artefact | Door | Verdict | Evidence (teaminal) |
|---|---|---|---|
| Joined teams | Graph `GET /me/joinedTeams` (no `$select`/`$top` — Graph 400s under delegated) | **GREEN** | `src/graph/teams.ts:45-54` |
| Channels | Graph `GET /teams/{id}/channels` `?$select=id,displayName,description,membershipType,isArchived` | **GREEN** | `src/graph/teams.ts:60-68` |
| **Channel messages** | Graph `/teams/.../messages` is **RED** — FOCI never issues `ChannelMessage.Read.All`; `AADSTS65002` blocks the upgrade. **GREEN via chatsvc** (see below) | **GREEN (chatsvc only)** | `src/graph/teams.ts:26-39, 94-108`; `src/graph/teamsChatsvc.ts:321-352` |
| Channel replies | Same chatsvc stream; a message is a reply iff `properties.parentmessageid` set and ≠ its own id | **GREEN (chatsvc)** | `teamsChatsvc.ts:251-255` |
| Chats (1:1/group/meeting) | Graph `GET /me/chats` | **GREEN** (yaams `teams.py` proves it live too) | — |
| Chat messages | Graph `GET /chats/{id}/messages`; chatsvc fallback for CA-gated tenants | **GREEN (graph), amber on CA-gated → chatsvc** | yaams `teams_chatsvc.py` exists for exactly this |
| Online meetings | `/me/onlineMeetings` | **still PROBE** — teaminal doesn't cover it | — |
| Team members | `/teams/{id}/members` | **PROBE** — teaminal sidesteps it, deriving identity from message MRI + `imdisplayname` instead | `teamsChatsvc.ts` roster build |

### The chatsvc door (this is what the priors call "try `teams` aud" but didn't pin down)

Channel + chat message **bodies** are read from the chat service, NOT Graph:

```
GET https://teams.microsoft.com/api/chatsvc/{region}/v1/users/ME/conversations/{conversationId}/messages
    ?pageSize=50&startTime=1&view=msnp24
```
(verified `teamsChatsvc.ts:325-330` — exact params are `pageSize`, `startTime=1`, `view=msnp24`)

- **`{conversationId}` is fed verbatim, same endpoint for both** (`teamsChatsvc.ts:328-330`):
  - **channel** → the Graph channel `id` (`19:…@thread.tacv2`). Enumerate via Graph, no translation.
  - **chat** → the chat `id` (`19:…@unq.gbl.spaces`). Same path, chatsvc handles both.
- **View is bare `msnp24`** (NOT the `supportsMessageProperties` variant the prior guessed).
  `msnp24` already returns `properties.parentmessageid` / `subject` / `emotions` — confirmed
  by the message parser at `teamsChatsvc.ts:135-154`. Don't over-spec the view string.
- **`{region}`** is mandatory, tenant-specific, a SHORT string (`emea`/`amer`/`apac`/`ind`/…),
  NOT a host. Derived from `POST /api/authsvc/v1.0/authz` → `regionGtms.chatService` host,
  then shortened by `regionFromHost()` (`teamsRegion.ts:59-69`); hard fallback `emea`
  (`teamsRegion.ts:25`). There's also a **partition** (`emea-02`) pulled from
  `regionGtms.middleTier` — only needed for the federation/external-search `mt/part/{...}`
  endpoints, not for chatsvc. **Gap to close:** the auth section never mentioned region;
  port `authsvc → region` into `owa_teams/region.py` (interim: per-profile `region` config).
- **Pagination:** `_metadata.backwardLink` (absolute URL, fetches OLDER messages) — follow
  verbatim; NOT Graph's `@odata.nextLink`, so `owa_core.http.paginate` won't apply as-is
  (needs a small `backwardLink` follower, like owa-sites' `paginate_sp`) (`teamsChatsvc.ts:349`).
- **Order:** chatsvc returns newest-first; teaminal reverses to chronological before
  returning (`teamsChatsvc.ts:373`). Channel reads also DROP replies (keep where
  `parentmessageid` absent or == `id`); chat reads keep everything (chats are flat).

### chatsvc auth — two doors, attribution corrected against source

- **skypetoken (teaminal's actual path, verified):** mint a spaces-scope bearer
  (`--scope https://api.spaces.skype.com/.default`, fallback `https://teams.microsoft.com/.default`),
  `POST /api/authsvc/v1.0/authz` with an empty `{}` body, read the skypeToken out of
  `skypeToken` | `tokens.skypeToken` | `tokens.token` (`teamsFederation.ts:152-172`), then
  send it to chatsvc as **both** `Authentication: skypetoken=<tok>` AND `x-skypetoken: <tok>`
  (`teamsFederation.ts:323-324`). **This one call ALSO returns `regionGtms`** — so the
  skypetoken door solves auth + region together. skypeToken caches per-profile, ~1h.
- **ic3-bearer (yaams' path, simpler if it works):** `owa-piggy --audience ic3` →
  `Authorization: Bearer …`. yaams' `teams_chatsvc.py` uses this for *chat* messages live;
  teaminal only uses ic3 for a conversation-existence probe (`teamsFederation.ts:546`), NOT
  for reading messages — so whether ic3-bearer reads *channel* messages is genuinely unconfirmed.

  → **PROBED LIVE 2026-06-02 (acme / emea) — ic3-bearer is GREEN.** `owa-piggy token
  --audience ic3` against `GET …/chatsvc/emea/v1/users/ME/conversations/{channelId}/messages`
  returns **200** with the full message stream on every channel tested (31 channels across 8
  teams). **Build on the ic3 bearer; no skypetoken machinery needed for reads.** region was
  hardcoded `emea` for the probe and worked (acme is an EU tenant) — still port proper
  region resolution for non-EU profiles. owa-teams' `auth.py` registers `ic3` (+ `csa` for the
  CA-gated fallback) audiences (owa-graph's `AUDIENCE_API_BASE` lists neither yet, though
  owa-piggy mints them) + the dynamic regional chatsvc base. Graph `/replies` was also probed:
  **403 `requires ChannelMessage.Read.All`** — confirming teaminal's reply path is walled here.

### CA-gated fallback (CSA bootstrap) — for tenants where even Graph `/teams` is walled

`GET https://teams.microsoft.com/api/csa/{region}/api/v1/teams/users/me` returns teams
*and* their channels in one call (`teamsCsa.ts:313-324`, `--audience csa`). Phase 2 —
ship the Graph enumeration first; add CSA only when a profile 403s on `/me/joinedTeams`.

### Channel threading — PROBED LIVE 2026-06-02, the model is `rootMessageId` (NOT parentmessageid)

teaminal threads channels on `properties.parentmessageid` and fetches replies via the Graph
`/replies` door. **Both are wrong/dead under owa-piggy** — verified against live acme data:

- Graph `/replies` → **403** (`ChannelMessage.Read.All`, never issued by FOCI).
- `properties.parentmessageid` is **`null` on every channel message in this tenant** — so
  teaminal's filter `!parentmessageid || parentmessageid === id` passes *everything*, leaking
  replies into its root list with no threading. (Latent teaminal bug; flag it upstream.)

The actual model — the flat chatsvc `/conversations/{channelId}/messages` stream **already
contains roots AND replies interleaved**, ordered by a monotonic top-level `sequenceId`, and
every message carries a top-level **`rootMessageId`**:

```
seq id            rootMessageId  →  ROOT (rootMessageId == id, carries `subject`)
 8  1665994613428 1665994613428  →  ROOT  "TV-aksjonen 2022 …"
 9  1666190353792 1665994613428  →  reply
10  1667287175358 1665994613428  →  reply
11  1667290632494 1665994613428  →  reply
12  1677568668800 1677568668800  →  ROOT  "Frivillig informasjonsmøte …"
13  1677568965655 1677568668800  →  reply
```

So **one paginated pass reconstructs every thread — no N+1, no `/replies`, no `;messageid=`
sub-conversation calls** (the `{channelId};messageid={rootId}` sub-conversation door also
works/200s but is unnecessary given `rootMessageId`). The wire shape owa-teams emits per
message MUST therefore expose **`rootMessageId`**, `id`, `sequenceId`, `subject`, plus
`team_id`/`channel_id`/`channel_name`. Downstream the yaams adapter sets:

```python
root_id  = msg["rootMessageId"] or msg["id"]
is_reply = root_id != msg["id"]
thread_id = f"{channel_id}:{root_id}"            # clusters root + its replies
subject   = root_subject_for(root_id)            # only roots carry `subject`
```

(Chats stay flat — `thread_id = chat_id` as today. Only channels need rootMessageId grouping.)

## Meetings — meeting chats × owa-cal (the model, refined 2026-06-02)

**A Teams meeting IS a meeting chat.** `chatType == 'meeting'`, thread id
`19:meeting_<base64>@thread.v2`. The chat is the meeting's durable hub: its messages,
its files, its roster. So `owa-teams meetings` is fundamentally a **filtered chats
view**, not a new endpoint.

- **Detection is free on Graph.** Graph `/chats` returns `chatType`
  (`oneOnOne | group | meeting | unknownFutureValue`) natively — filter `chatType eq 'meeting'`.
  On the CSA fallback path it's derived heuristically by `csaChatType()`
  (`teamsCsa.ts:177-183`: `threadType`+`chatType` contains "meeting"). Either door identifies them.
- **But the chat object carries NO meeting metadata.** teaminal confirms this the hard way:
  it never touches calendar or onlineMeeting, so a meeting chat has **no organizer, no
  start/end, no subject beyond `topic`, no attendee list, no join URL**. The agents grepped
  the whole graph layer — zero `onlineMeeting`/`organizer`/`eventId` references.
- **`/me/onlineMeetings` is the obvious-but-wrong door.** Needs `OnlineMeetings.Read`,
  almost certainly NOT in the One Outlook Web client's fixed scope set → expect RED. Probe it
  in Phase 0, but **do not design around it.**

### The owa-cal join (this is the "overlap with owa-cal" the build is for)

Meeting *metadata* (subject, organizer, **attendees**, start/end) lives on the **calendar
event**, which owa-cal already reads with the `outlook` token that WORKS. The link key is the
**meeting thread id**, which is embedded in the event's online-meeting join URL:

```
event.OnlineMeeting.JoinUrl
  = https://teams.microsoft.com/l/meetup-join/19%3ameeting_<base64>%40thread.v2/0?context=...
                                              └────────── URL-decode ──────────┘
  → 19:meeting_<base64>@thread.v2   == the meeting chat id
```

So: list meeting chats (Teams) → list online-meeting events in a window (owa-cal) →
parse the thread id out of each event's `JoinUrl` → **join on thread id**. The result is a
unified meeting: chat hub + messages (Teams side) + subject/time/organizer/attendees (cal side).

- **Concrete owa-cal dependency:** `owa_cal/cli.py:_EVENTS_SELECT` does NOT currently select
  `OnlineMeeting`/`IsOnlineMeeting` (verified — it stops at `…OriginalEndTimeZone`). The join
  needs them. Either extend that shared select (cheap, additive, also useful to owa-cal's own
  output) or have owa-teams issue its own event query selecting `OnlineMeeting,IsOnlineMeeting`.
- **Best-effort, by design.** Ad-hoc "Meet now" chats have no calendar event (no enrichment);
  scheduled events outside the `--from/--to` window won't match. `meetings` lists the *chats*
  and enriches where an event matches — don't drop un-matched meeting chats.
- **Verbs:**
  - `meetings [--from --to]` — meeting chats, enriched with cal metadata where matched.
  - `meetings <chat-id> --messages` — the meeting chat's transcript via chatsvc.
  - the cal-event ↔ thread-id resolver is a small shared helper (`meetings.py:thread_id_from_joinurl`).

## Other Teams artefacts (bonus read-only verbs — all clean, stateless GETs)

teaminal implements a lot more than teams/channels/chats/messages. The agents ranked which
port cleanly to a stateless CLI. In rough priority:

| Verb | Surface | Endpoint | Audience | Verdict |
|---|---|---|---|---|
| `search <q>` | tenant-wide message search | `POST graph /search/query` `entityTypes:[chatMessage]` | graph | **GREEN, do it** — single-shot, ready-to-display hits (`messageSearch.ts`) |
| `activity` | the notification-bell feed (mentions/replies/reactions) | `GET csa /api/v3/teams/users/me/updates` (opaque `syncState` cursor) | csa | **GREEN** — clean, cursor-paginated (`teamsActivity.ts:253-333`) |
| `presence [oids…]` | rich presence (avail/activity/OOO/device) | `POST presence.teams.microsoft.com /v1/presence/getpresence/` | presence-scope | **GREEN** — bulk POST, works on FOCI where Graph `Presence.Read` 403s (`teamsPresence.ts`) |
| `find-user <email>` | federated/external people search | `POST mt/part/{region}/beta/users/searchV2` | spaces | amber — needs partition + is really a chat-create helper (`teamsExternalSearch.ts`) |
| (files/images) | inline media via AsyncGW | `asyncgw.teams.microsoft.com/.../objects/…` | skype/ic3 | **EXCLUDE v1** — session-stateful, IDs only live inside message bodies |
| (realtime) | trouter websocket push | `wss://…trouter…` | ic3 | **EXCLUDE** — long-lived WS, not a stateless CLI shape |

`search` + `activity` are the two standout adds — both are things you genuinely can't get
ergonomically today, and both are clean reads. Treat them as fast-follows after the core
teams/channels/chats/messages/meetings surface lands.

## Steps (build only what Phase 0 greenlit)

**Phase 1 — core surface (Graph + chatsvc).** Ship this first; it's the 90%.

- [ ] Scaffold `src/owa_teams/` per `docs/new-tool-onboarding.md` (mirror
      `owa_sites` layout: `__init__.py`, `__main__.py`, `cli.py`, `api.py`,
      `auth.py`, `config.py`, `format.py`, `teams.py` domain module, `AGENTS.md`).
      Add a `chatsvc.py` (message reads + `backwardLink` follower) and `region.py`.
- [ ] `auth.py`: register the audiences owa-graph lacks — `ic3`, `csa`, spaces
      (`https://api.spaces.skype.com`), `presence` — plus the **dynamic regional
      chatsvc base** `https://teams.microsoft.com/api/chatsvc/{region}`. Default
      `audience='graph'`. Reuse `owa_graph.auth` shape; do NOT fork owa-piggy.
- [ ] `region.py`: port `authsvc → regionGtms.chatService → regionFromHost()`
      (`teamsRegion.ts:59-69`); hard fallback `emea`; cache per profile; allow a
      `region` config override. The skypetoken door (below) returns `regionGtms` in
      the same call, so prefer doing both together.
- [ ] `chatsvc.py`: the message door. `GET …/chatsvc/{region}/v1/users/ME/conversations/{id}/messages?pageSize=50&startTime=1&view=msnp24`.
      Auth: try ic3-bearer, fall back to skypetoken (`Authentication: skypetoken=` +
      `x-skypetoken`, minted via `authsvc`). Follow `_metadata.backwardLink`; reverse to
      chronological; drop channel replies (keep where `parentmessageid` absent/==id).
      Message normalizer: `id, parentmessageid, from(oid via parseFrom), imdisplayname,
      createdDateTime(originalarrivaltime||composetime), body(content, html→text),
      subject, reactions, deleted/edited` — keep `team_id`/`channel_id`/`channel_name`
      + `parentmessageid` on the wire for the yaams threading model above.
- [ ] `teams.py`: Graph path builders + normalizers, with the verified quirks —
      - team: `GET /me/joinedTeams` **with NO `$select`/`$top`** (Graph 400s on them
        under delegated auth — `teams.ts:45-54`). Fields: `id, displayName, description`.
      - channel: `GET /teams/{id}/channels?$select=id,displayName,description,membershipType,isArchived`.
      - chat: `GET /chats?$expand=lastMessagePreview&$top=50&$orderby=lastMessagePreview/createdDateTime desc`
        (NOT `lastUpdatedDateTime`). `chatType` comes back natively. Member roster via
        `GET /chats/{id}?$expand=members` (cap 25) or `$batch` (≤20 chats/call) for bulk.
      - identity: MRI `8:orgid:{guid}` → strip to the guid for `userId`; keep raw MRI as `id`.
- [ ] CLI verbs (all read-only v1):
      - `teams` / `ls` — joined teams (default command)
      - `channels --team <id|name>` — resolve name→id via a cached `teams`
      - `chats [--type oneOnOne|group|meeting]`
      - `messages --chat <id> | --team <id> --channel <id> [--top N]` (chatsvc)
      - `members --chat <id>` (Graph roster; `--team` member listing is a separate PROBE)
- [ ] `meetings` verb (Teams × owa-cal join, per the Meetings section): list
      meeting chats, parse thread id from each cal event's `OnlineMeeting.JoinUrl`,
      join on thread id, enrich with subject/organizer/start/end/attendees.
      **Pre-req:** extend owa-cal's `_EVENTS_SELECT` (or a local query) with
      `OnlineMeeting,IsOnlineMeeting`. `meetings <id> --messages` → chatsvc transcript.
- [ ] HTTP + pagination via `owa_core.http` for Graph (`@odata.nextLink`); chatsvc's
      `backwardLink` and CSA's `continuationToken` each need their own small follower
      (model on owa-sites' `paginate_sp`).
- [ ] Multi-profile fan-out: honour the standard profile args
      (`owa_core.profiles_args` / `modes.py`) so `--all-profiles` works like the rest.
- [ ] `--pretty` renderers: teams/channels as tables; messages threaded/by-author
      (use `imdisplayname` — no Graph user lookup); chats with member names; meetings
      grouped by day with organizer + attendee count.
- [ ] Tests under `src/tests/teams/`: full onboarding minimum set — mock the Graph,
      chatsvc, and authsvc boundaries; cover `/me/joinedTeams` no-query, the
      `JoinUrl → thread id` parser, the meeting↔event join, reply-vs-root, html→text,
      and the `backwardLink` follower; scanner + stdlib checker include the new pkg.

**Phase 2 — fallbacks + bonus verbs (only as needed).**

- [ ] CSA bootstrap fallback (`teamsCsa.ts`): `GET csa /api/v1/teams/users/me`
      (teams+channels) + `/api/v2/.../chats` (chats w/ member names, `continuationToken`).
      Wire in only when a profile 403s on Graph `/me/joinedTeams` (CA-gated / ic3-primary
      accounts). `csaChatType()` gives meeting detection on this path.
- [ ] `search <q>` — `POST graph /search/query` `entityTypes:[chatMessage]`. Clean win.
- [ ] `activity` — `GET csa /api/v3/teams/users/me/updates`, opaque `syncState` cursor.
- [ ] `presence [oids…]` — `POST presence.teams.microsoft.com/v1/presence/getpresence/`
      (Graph `/me/presence` as fallback).
- [ ] EXCLUDED v1: files/inline media (AsyncGW — session-stateful) and realtime (trouter WS).

**Cross-cutting.**

- [ ] Register everywhere: `pyproject.toml` (packages + `owa-teams` script +
      coverage), `owa_core/registry.py` CONSUMER_TOOLS, README table, `docs/teams.md`,
      CHANGELOG, root AGENTS.md index, `owa_teams/AGENTS.md`, `check_docs_sync.py` DOCS
      map, shell completions.
- [ ] Acceptance per onboarding doc; bump hardcoded version in `test_version.py`
      if cutting a release (see [[owa-tools-release-gotchas]]).

## Notes

- **No breaking change to owa-graph.** Leave its teams/channels sniffers in place;
  owa-teams is additive sugar over the same calls (consistent with
  [[owa-cli-rename-philosophy]] — additive, never breaking).
- **Reconcile the memory.** [[owa-piggy-token-scope-limits]] currently says
  "owa-teams folded into owa-graph". Update that verdict after Phase 0 to reflect
  the green subcommand set (and whether the `teams`-audience message door opened).
- Message bodies are HTML — strip to text for the wire shape, keep raw under a
  `--raw`/`--json` passthrough.
- Times are UTC; render in the profile/default tz, reusing owa-cal's tz handling
  rather than re-implementing.
- Writes (post a message, create a chat) are explicitly **out of scope for v1** —
  read surface is the 90% use case and avoids the destructive-confirm machinery.
- `owa-shifts` (Teams Shifts) already references sharing `/me/joinedTeams` team
  discovery with owa-teams "if it lands first" — land that helper here cleanly so
  owa-shifts can reuse it if it ever unblocks.

## Fast-follows the yaams `teams_channels` adapter wants (added 2026-06-02)

yaams' channel ingestion (`yaams/ingest/teams_channels.py`, shipped) shells out
to `owa-teams teams|channels|messages`. Its v1 works against the current
(documented) contract — chronological rows carrying `threadId`,
`rootMessageId`, `isReply`, `from{id,name,mri}`, `timestamp`, `subject`,
`content`, `teamId`, `channelId`. Two flags on the `messages` verb would let it
drop its workarounds:

- **`messages --since <iso>`** — stop following `backwardLink` once a page
  predates the cutoff. Today yaams fetches `--limit` pages and filters
  `timestamp <= cutoff` adapter-side, so a cold start of a busy channel can miss
  history older than `limit_pages × ~50` messages. `--since` removes that gap and
  cuts pages fetched.
- **`messages --region <emea|amer|…>`** — region is currently resolved from
  owa-teams' own (single-valued) config, but yaams ingests multiple profiles that
  may live in different regions. A per-call `--region` (read through to the
  chatsvc base) lets the adapter pass it per profile. All current profiles are
  `emea`, so yaams v1 works without it; add before onboarding a non-EU profile.

Also: yaams holds the channel id→name map from its `channels` call and stamps
the name itself, since `messages` rows don't carry `channelName`. Adding
`channelName`/`teamName` to the message wire shape would let the adapter drop
that bookkeeping (nice-to-have, not blocking).

**DONE 2026-06-03 — 429 Retry-After ride-through.** The fan-out tripped
chatsvc's rate limiter and `owa-teams` aborted the verb on a 429 (dropping a
team's channels); yaams added outer exponential backoff in v0.3.2. The proper
fix now lands here too: `api.graph_get` / `graph_paginate` / `chatsvc_messages`
carry a default retry budget (`api.DEFAULT_RETRY=3`) so `owa_core.http` honors
`Retry-After` in-process (capped 60s) before surfacing the 429. The two layers
compose: owa-teams rides transient limits; if it still exits non-zero, yaams
retries the whole verb. Still open: `messages --since` and `messages --region`.
