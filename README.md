# owa-cal

Calendar CLI for Outlook / Microsoft 365. Read, create, update and delete events from the terminal.
Pipe-friendly JSON by default, `--pretty` for humans.

```sh
brew install damsleth/tap/owa-cal
owa-cal events --pretty
```

---

## Happy-path setup (no app registration)

[`owa-piggy`](https://github.com/damsleth/owa-piggy) owns the token
lifecycle; owa-cal just shells out to it on every call. The full
first-run flow:

```sh
# 1. Install both
brew install damsleth/tap/owa-piggy damsleth/tap/owa-cal

# 2. Seed owa-piggy once from your browser (walks you through it)
owa-piggy setup

# 3. Go
owa-cal events --pretty
```

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

Same shape on `create` / `update` (returns the single normalized
event), and on `categories` (returns `[{"name": ..., "color": ...}]`).

---

## Commands

```sh
owa-cal events --pretty                       # today
owa-cal events --week 16 --pretty             # ISO week
owa-cal events --from 2026-04-14 --to 2026-04-18 --pretty
owa-cal events --search "standup" --pretty

owa-cal create --subject "lunsj" --start 11:00 --end 11:30 --category "CC LUNCH"
owa-cal update --id <event-id> --category "ProjectX"
owa-cal delete --id <event-id>

owa-cal categories                            # JSON
owa-cal categories --pretty                   # aligned table
```

---

## Auth

Two paths:

- **owa-piggy bridge (default)** - owa-cal shells out to
  [`owa-piggy`](https://github.com/damsleth/owa-piggy), which
  piggybacks on OWA's public SPA client. No app registration needed;
  owa-cal stores no refresh token. Optional `owa_piggy_profile` pins a
  named owa-piggy profile.
- **With an app registration** - set `OUTLOOK_APP_CLIENT_ID`,
  `OUTLOOK_REFRESH_TOKEN`, and `OUTLOOK_TENANT_ID` in the config file
  and owa-cal talks to the AAD token endpoint directly.

Config lives at `~/.config/owa-cal/config`:

```
# Default (owa-piggy) path - optional, pins a profile alias
owa_piggy_profile="work"

# App-registration path (optional, mutually exclusive)
OUTLOOK_APP_CLIENT_ID=""
OUTLOOK_REFRESH_TOKEN=""
OUTLOOK_TENANT_ID=""
```

`OUTLOOK_APP_CLIENT_ID` can be overridden via the environment. The
refresh token / tenant id on the app-registration path live
exclusively in the config file.

---

## Dependencies

- Python 3.8+ (stdlib only - no `pip install` required at runtime)
- [`owa-piggy`](https://github.com/damsleth/owa-piggy) unless you
  bring your own app registration

## Development

```sh
git clone https://github.com/damsleth/owa-cal
cd owa-cal
pip install -e '.[test]'
pytest -q
```

See [`AGENTS.md`](AGENTS.md) for repo layout and ground rules.

## Disclaimer

```
Personal tooling. Stores a delegated refresh token on disk.
If you don't know why that might be a bad idea, don't use it.
```
