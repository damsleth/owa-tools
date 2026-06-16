# owa-cal

Calendar CLI for Outlook / Microsoft 365. Read, create, update, delete and RSVP to events from the terminal.
Pipe-friendly JSON by default, `--pretty` for humans.

```sh
brew install damsleth/tap/owa-tools      # ships owa-cal + the whole suite
owa-cal events --pretty
```

Or one-shot, no install, no on-disk state:

```sh
OWA_REFRESH_TOKEN=1.AQ... OWA_TENANT_ID=<tenant-id-or-domain> \
  uvx --from owa-tools owa-cal events --pretty
```

`uvx --from owa-tools` pulls the suite (and owa-piggy as a transitive
dep) into a throwaway venv. The two env vars feed straight through to owa-piggy's
env-only mode - nothing is written to `~/.config/`. Useful on a
borrowed laptop, in a CI job, or for a one-off script. See
[Single-line uvx](#single-line-uvx-no-install-no-disk-state) for how
to scrape the two values from a browser session.

---

## Happy-path setup (no app registration)

[`owa-piggy`](https://github.com/damsleth/owa-piggy) owns the token
lifecycle; owa-cal just shells out to it on every call. The full
first-run flow:

```sh
# 1. Install both
brew install damsleth/tap/owa-piggy damsleth/tap/owa-tools

# 2. Seed owa-piggy once from your browser (walks you through it)
owa-piggy setup

# 3. Go
owa-cal events --pretty
```

owa-piggy and owa-tools version independently. owa-cal expects any
owa-piggy >= 0.7.1 and sanity-checks the version on first call.

Multi-account: seed a named owa-piggy profile and pin it in owa-cal's
config.

```sh
owa-piggy setup --profile work
owa-cal config --profile work
```

`--profile` also works as a one-shot override:
`owa-cal --profile home events`.

Refresh tokens rotate on every call and are persisted by owa-piggy in
its own profile store. owa-cal stores no refresh token on this path;
`owa-piggy --reseed --profile <alias>` refreshes the token headlessly
when the 24h hard-expiry lapses, and owa-cal picks up the new token
on the next call automatically.

---

## The output contract

**JSON on stdout, logs on stderr.** Every read command emits parseable
JSON by default; `--pretty` is a human override that goes to stdout
too. That means the entire CLI composes with `jq`:

```sh
owa-cal events
```

```json
[
  {
    "id": "AAMkAGI1...redacted",
    "subject": "Standup",
    "start": "2026-04-20T09:00:00",
    "end": "2026-04-20T09:30:00",
    "categories": ["ProjectX"],
    "location": "Teams",
    "showAs": "Busy",
    "isAllDay": false
  },
  {
    "id": "AAMkAGI2...redacted",
    "subject": "Lunsj",
    "start": "2026-04-20T11:00:00",
    "end": "2026-04-20T11:30:00",
    "categories": ["CC LUNCH"],
    "location": "",
    "showAs": "Busy",
    "isAllDay": false
  }
]
```

Timestamps are normalized to your local timezone. Field names in the
output are stable lowercase; the backend is Outlook REST v2 (PascalCase
upstream) but owa-cal hides that detail.

```sh
owa-cal events | jq '.[].subject'
owa-cal events --date tomorrow | jq '[.[] | select(.showAs == "Busy")] | length'
owa-cal events --week 16 | jq 'group_by(.start | .[0:10]) | map({day: .[0].start[0:10], count: length})'
```

`events` caps at a single page by default. Pass `--all` to follow
`@odata.nextLink` until every event in the window is returned; `--limit`
still controls the page size (`$top`) requested per round-trip. Output
shape is unchanged. (Against a webcal/iCal `--profile`, `--all` is a
no-op: the feed is always fetched in full.)

```sh
owa-cal events --from 2026-01-01 --to 2026-12-31 --all | jq length
```

Same shape on `create` / `update` (returns the single normalized
event), and on `categories` (returns `[{"name": ..., "color": ...}]`).

`respond` sends a meeting reply (`accept` / `decline` / `tentative`) to an
invite and emits `{"id": ..., "action": ..., "notified": true}` on success.
The organizer is notified by default; pass `--no-notify` to record the
response without sending a reply, and `--comment "<text>"` to include a note.
Outlook returns no body for these actions, so the JSON is owa-cal's own
confirmation envelope, not an event.

---

## Commands

```sh
owa-cal events --pretty                       # today
owa-cal events --week 16 --pretty             # ISO week (absolute)
owa-cal events --week last --pretty           # previous week (also: --week -1)
owa-cal events --week next                     # next week (also: --week +1)
owa-cal events --month --pretty               # this calendar month
owa-cal events --month next                    # next month (also: --month +1)
owa-cal events --year +1 --pretty             # the whole of next year
owa-cal events --date monday+1                 # next Monday
owa-cal events --from 2026-04-14 --to 2026-04-18 --pretty
owa-cal events --search "standup" --pretty

owa-cal create --subject "lunsj" --start 11:00 --end 11:30 --category "CC LUNCH"
owa-cal update --id <event-id> --category "ProjectX"
owa-cal delete --id <event-id>

owa-cal respond --id <event-id> --action accept              # RSVP to an invite
owa-cal respond --id <event-id> --action decline --comment "conflict"
owa-cal respond --id <event-id> --action tentative --no-notify

owa-cal categories                            # JSON
owa-cal categories --pretty                   # aligned table

owa-cal profiles list                         # local + broker profile view
owa-cal refresh                               # force token refresh
owa-cal config --profile work                 # pin a profile
```

Events carry opaque ids: address one via `--id` or as a bare positional
argument (`owa-cal delete <id>` == `owa-cal delete --id <id>`).

### Relative & semantic period values

`events` (and `owa-sched`) accept relative values for the period flags, so you
rarely need to look up an absolute ISO week number:

| Flag | Absolute | Relative vocabulary |
| --- | --- | --- |
| `--week` | `16` | `current`/`this`, `last`/`prev`, `next`, `+n`, `-n` |
| `--month` | `1`–`12` | `current`/`this`, `last`/`prev`, `next`, `+n`, `-n` (bare `--month` = current) |
| `--year` | `2026` (≥ 100) | `current`/`this`, `last`/`prev`, `next`, `+n`, `-n` |
| `--date` / `--from` / `--to` | `2026-04-18` | `today`/`tomorrow`/`yesterday`, `+n`/`-n` (days), `monday`…`sunday` (this ISO week), `monday+1` / `friday-2` (weekday ± weeks) |

Precedence when several are given: `--from`/`--to` > `--date` > `--week` >
`--month` > `--year` (alone = whole year) > today. `--year` combines with
`--week`/`--month` to set the year; combining flags from different tiers (e.g.
`--week` with `--month`) is a usage error. Bare `--year` below 100 is rejected
as ambiguous — use a full year or a signed offset.

---

## Machine / agent surface

Every owa binary exposes the same machine surface (see
[agent-integration.md](agent-integration.md) for the full contract):

- `owa-cal schema [<command>]` - JSON command schema (one command if named)
- `owa-cal --help --json` - the same schema via the help flag
- `--agent` - wrap JSON stdout in a stable `{"_owa": ..., "data": ...}`
  envelope (or set `OWA_AGENT=1`)
- `--err-json` - structured JSON errors on stderr (or `OWA_ERR_JSON=1`)
- `--doctor [--json]` - this tool's health / redaction doctor payload

---

## Auth

owa-cal shells out to [`owa-piggy`](https://github.com/damsleth/owa-piggy)
for a fresh access token on every call. owa-piggy piggybacks on OWA's public
SPA client (no Azure AD app registration needed) and owns the refresh-token
lifecycle. owa-cal stores no refresh token of its own - at most an
`owa_piggy_profile` alias. Audience: `outlook` (Outlook REST).

Config lives at `~/.config/owa-cal/config` and holds only non-secret
preferences:

```
# Optional - pins which owa-piggy profile owa-cal uses by default
owa_piggy_profile="work"
```

### Single-line uvx (no install, no disk state)

`uvx --from owa-tools owa-cal` pulls the suite into an ephemeral venv
and never writes to `~/.config/`. Pair it with owa-piggy's env-only mode
and you have a one-shot, fully portable invocation:

```sh
OWA_REFRESH_TOKEN=1.AQ... \
OWA_TENANT_ID=<tenant-id-or-domain> \
  uvx --from owa-tools owa-cal events --pretty
```

Variables go to owa-piggy via subprocess env inheritance; owa-cal
itself never sees the token. `OWA_PROFILE` is honored if you also
have profiles on disk, but is unnecessary in env-only mode.

To scrape the two values out of a browser session (Edge -> outlook.cloud.microsoft, F12 -> Console):

```js
const find = s => Object.keys(localStorage).find(k => k.includes(s))
const parse = s => JSON.parse(localStorage[find(s)])
const rt = parse('|refreshtoken|'), it = parse('|idtoken|')
console.log(`OWA_REFRESH_TOKEN=${rt.secret || rt.data}
OWA_TENANT_ID=${it.realm || find('|idtoken|').split('|')[5]}`)
```

Caveats:

- Plain Chromium browsers (vanilla Chrome/Brave) store a session-bound
  token AAD won't accept. Use Microsoft Edge.
- The refresh token AAD returns rotates on every exchange. In env-only
  mode owa-piggy prints a `NOTE:` to stderr noting the new token; copy
  it back into your env if you plan another call. Persistent use
  belongs in `owa-piggy setup`, not env vars.
- Tokens on a command line (e.g. `OWA_REFRESH_TOKEN=... uvx ...`) end
  up in shell history and `ps aux`. Source them from a file
  (`set -a; . secrets.env; set +a; uvx --from owa-tools owa-cal events`) or your
  password manager's CLI.

#### For agents

The same invocation is the cleanest way for an LLM agent or automation
to read/write a calendar without persistent setup:

```sh
OWA_REFRESH_TOKEN=$RT OWA_TENANT_ID=$TID \
  uvx --quiet --from owa-tools owa-cal events --from 2026-04-26 --to 2026-05-03
```

Useful contract for agent code:

- stdout is JSON (omit `--pretty`); stderr is logs.
- exit codes follow the suite taxonomy: `0` success, `2` usage, `10`
  network, `11` auth-expired, `12` scope, `13` not-found, `14`
  rate-limited, `15` conflict, `20` internal. See
  [agent-integration.md](agent-integration.md).
- `--quiet` on `uvx` suppresses the `Installed N packages` line so
  stdout stays clean for `jq` / `json.loads`.
- pin a version for reproducibility: `uvx --from 'owa-tools==0.2.1'
  owa-cal events`.
- short-lived only. Refresh tokens rotate on every exchange and have
  nowhere to go in env-only mode; for an agent that calls more than
  once across the 24h sliding window, run `owa-piggy setup --profile
  agent` once on the host and use `OWA_PROFILE=agent uvx --from
  owa-tools owa-cal ...` instead - owa-piggy then handles rotation and
  caching.

---

## Dependencies

- Python 3.10+
- [`owa-piggy`](https://github.com/damsleth/owa-piggy), the auth broker

## Development

owa-cal ships in the `owa-tools` suite repository:

```sh
git clone https://github.com/damsleth/owa-tools
cd owa-tools
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

See [`AGENTS.md`](../AGENTS.md) for repo layout and ground rules.

## Disclaimer

```
Personal tooling. owa-cal holds no refresh token of its own - tokens
are owa-piggy's responsibility, scoped to its profile store. owa-cal's
own config file holds only non-secret preferences. If you don't know
why piggybacking on a browser session might be a bad idea, don't use it.
```
