# cal-cli

Calendar CLI for Outlook / Microsoft 365. Read, create, update and delete events from the terminal.
Pipe-friendly JSON by default, `--pretty` for humans.

```sh
brew install damsleth/tap/cal-cli
cal-cli events --pretty
```

---

## Happy-path setup (no app registration)

If you have [`owa-piggy`](https://github.com/damsleth/owa-piggy) installed,
cal-cli delegates auth to it and you don't need an Azure AD app
registration. The full first-run flow:

```sh
# 1. Install both
brew install damsleth/tap/owa-piggy
brew install damsleth/tap/cal-cli

# 2. Seed owa-piggy once from your browser (walks you through it)
owa-piggy --setup

# 3. Point cal-cli at the same token + tenant
cal-cli config \
  --refresh-token "$(owa-piggy --json | jq -r .refresh_token)" \
  --tenant-id     "$(owa-piggy --json | jq -r .tenant_id)"

# 4. Go
cal-cli events --pretty
```

Refresh tokens rotate on every call; cal-cli persists the rotated
value back to `~/.config/cal-cli/config` atomically. Use the CLI once
a day and the sliding window keeps it alive. (The underlying SPA
refresh token still has a 24h hard-expiry - when you hit it,
`owa-piggy --reseed` fetches a fresh one headlessly from Edge.)

---

## The output contract

**JSON on stdout, logs on stderr.** Every read command emits parseable
JSON by default; `--pretty` is a human override that goes to stdout
too. That means the entire CLI composes with `jq`:

```sh
cal-cli events
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

Timestamps are normalized to your local timezone. Field names are
stable regardless of whether the backend speaks Outlook REST
PascalCase or Graph camelCase.

```sh
cal-cli events | jq '.[].subject'
cal-cli events --date tomorrow | jq '[.[] | select(.showAs == "Busy")] | length'
cal-cli events --week 16 | jq 'group_by(.start | .[0:10]) | map({day: .[0].start[0:10], count: length})'
```

Same shape on `create` / `update` (returns the single normalized
event), and on `categories` (returns `[{"name": ..., "color": ...}]`).

---

## Commands

```sh
cal-cli events --pretty                       # today
cal-cli events --week 16 --pretty             # ISO week
cal-cli events --from 2026-04-14 --to 2026-04-18 --pretty
cal-cli events --search "standup" --pretty

cal-cli create --subject "lunsj" --start 11:00 --end 11:30 --category "CC LUNCH"
cal-cli update --id <event-id> --category "ProjectX"
cal-cli delete --id <event-id>

cal-cli categories                            # JSON
cal-cli categories --pretty                   # aligned table
```

---

## Auth

Two paths:

- **With an app registration** - set `OUTLOOK_APP_CLIENT_ID` and
  cal-cli talks to the AAD token endpoint directly.
- **Without** - cal-cli shells out to
  [`owa-piggy`](https://github.com/damsleth/owa-piggy), which
  piggybacks on OWA's public SPA client. No app registration needed.

Config lives at `~/.config/cal-cli/config`:

```
OUTLOOK_REFRESH_TOKEN="1.AQ..."
OUTLOOK_TENANT_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
OUTLOOK_APP_CLIENT_ID=""   # optional
```

Env vars (`OUTLOOK_REFRESH_TOKEN`, `OUTLOOK_TENANT_ID`,
`OUTLOOK_APP_CLIENT_ID`) override the config file.

---

## Dependencies

- Python 3.8+ (stdlib only - no `pip install` required at runtime)
- [`owa-piggy`](https://github.com/damsleth/owa-piggy) unless you
  bring your own app registration

## Development

```sh
git clone https://github.com/damsleth/cal-cli
cd cal-cli
pip install -e '.[test]'
pytest -q
```

See [`AGENTS.md`](AGENTS.md) for repo layout and ground rules.

## Disclaimer

```
Personal tooling. Stores a delegated refresh token on disk.
If you don't know why that might be a bad idea, don't use it.
```
