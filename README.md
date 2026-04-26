# owa-cal

Calendar CLI for Outlook / Microsoft 365. Read, create, update and delete events from the terminal.
Pipe-friendly JSON by default, `--pretty` for humans.

```sh
brew install damsleth/tap/owa-cal
owa-cal events --pretty
```

Or one-shot, no install, no on-disk state:

```sh
OWA_REFRESH_TOKEN=1.AQ... OWA_TENANT_ID=<tenant-id-or-domain> \
  uvx owa-cal events --pretty
```

`uvx` pulls owa-cal (and owa-piggy as a transitive dep) into a
throwaway venv. The two env vars feed straight through to owa-piggy's
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
brew install damsleth/tap/owa-piggy damsleth/tap/owa-cal

# 2. Seed owa-piggy once from your browser (walks you through it)
owa-piggy setup

# 3. Go
owa-cal events --pretty
```

owa-piggy and owa-cal version independently. owa-cal expects any
owa-piggy >= 0.6.0 and sanity-checks the version on first call.

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

### Single-line uvx (no install, no disk state)

`uvx owa-cal` pulls both packages into an ephemeral venv and never
writes to `~/.config/`. Pair it with owa-piggy's env-only mode and
you have a one-shot, fully portable invocation:

```sh
OWA_REFRESH_TOKEN=1.AQ... \
OWA_TENANT_ID=<tenant-id-or-domain> \
  uvx owa-cal events --pretty
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
  (`set -a; . secrets.env; set +a; uvx owa-cal events`) or your
  password manager's CLI.

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
Personal tooling. The default (owa-piggy bridge) path holds no
refresh token of its own - tokens are owa-piggy's responsibility,
scoped to its profile store. The optional app-registration path
does persist a delegated refresh token in owa-cal's config file.
If you don't know why either of those might be a bad idea, don't
use it.
```
