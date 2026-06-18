# owa-graph

Pipe-friendly Microsoft Graph CLI. One-off Graph queries with `owa-piggy`
auth, no token plumbing, no `az login`, no app registration required.

For a graphical Graph explorer, see [owa-tui](https://github.com/damsleth/owa-tui).

```sh
owa-graph GET /me
owa-graph GET '/users?$top=5' --pretty
owa-graph GET /users --all --ndjson | jq -c .displayName
owa-graph GET /users --search 'displayName:Bob' --count
owa-graph GET /me/messages --top 10 --select id,subject,from
owa-graph POST /me/sendMail --body @mail.json
owa-graph PATCH /me/messages/AAMk... --body '{"isRead":true}'
owa-graph PUT /me/drive/root:/notes.txt:/content --body @notes.txt
owa-graph DELETE /me/messages/AAMk...
owa-graph GET /me/drive/root/children --beta
owa-graph GET /me --curl | pbcopy
owa-graph GET me/events --audience outlook --pretty
owa-graph batch requests.json --pretty
owa-graph refresh
owa-graph config --profile work
```

Or, since v0.3, with curated shortcuts:

```sh
owa-graph me whoami
owa-graph mail list --unread --top 5 --pretty
owa-graph mail send --to foo@bar.com --subject hi --body 'hello'
owa-graph users find kim
owa-graph teams joined
owa-graph files list --pretty
```

## Install

Part of the `owa-tools` suite - one install ships owa-graph and the
whole suite plus the `owa-piggy` auth broker:

```sh
brew install damsleth/tap/owa-piggy damsleth/tap/owa-tools
# or: pipx install owa-piggy && pipx install owa-tools
# one-shot, no install: uvx --from owa-tools owa-graph GET /me
```

Run as `owa-graph ...` or via the umbrella `owa graph ...`.

## How it works

`owa-graph` is a thin verb-first wrapper around Microsoft Graph that
delegates auth to [`owa-piggy`](https://github.com/damsleth/owa-piggy):
on every call it shells out to `owa-piggy token --audience graph
--json`, takes the access token from stdout, and issues the HTTP
request with the right base URL and Bearer header.

- JSON on stdout, logs on stderr.
- `--pretty` prints tables for known collection shapes (users, groups,
  messages, drives, sites, calendars, planner / to-do tasks, …) and renders a
  single shallow object (e.g. `GET /me`) as a key/value table; it falls back to
  indented JSON for nested objects and anything else.
- `--curl` and `--az` print the equivalent shell command instead of
  executing - useful for sharing, scripting, or piping into `pbcopy`.
  By default the `Authorization` header renders a `$OWA_TOKEN`
  placeholder rather than the live bearer token, so the rendered command
  is safe to copy into the clipboard, paste into chat, or leave in shell
  history. Set the env var to run it (`export OWA_TOKEN=$(owa-piggy token
  --audience graph)`), or pass `--include-token` to inline the real
  token (avoid piping that to `pbcopy`).
- `--all` follows `@odata.nextLink` until exhausted; pair with
  `--ndjson` to stream items one per line through `jq`.
- `--count` and `--search` set Graph's `ConsistencyLevel: eventual`
  header so advanced directory queries don't 400.
- `--retry` honors `Retry-After` once on 429/503 (capped at 60s).
- `owa-graph batch <file|->` posts a JSON-batching request to `/$batch`;
  flat arrays are auto-wrapped in `{"requests": [...]}`.
- `--beta` switches to `https://graph.microsoft.com/beta`.
- `--audience` retargets at any FOCI audience `owa-piggy` knows about
  using the same query ergonomics. The 17 known audiences are:
  - `graph` - Microsoft Graph (default)
  - `outlook` - Outlook REST
  - `outlook365` - Outlook REST (alternate)
  - `teams` - Microsoft Teams middle-tier (mt/part, Skype audience)
  - `ic3` - Microsoft Teams chatsvc / asyncgw (modern)
  - `csa` - Microsoft Teams chat-service aggregator (updates, chatsAndTeams)
  - `presence` - Microsoft Teams presence / pubsub (ups)
  - `uis` - Microsoft Teams user/notification settings (nss)
  - `azure` - Azure Resource Manager
  - `keyvault` - Azure Key Vault
  - `storage` - Azure Blob/Table/Queue Storage
  - `sql` - Azure SQL
  - `substrate` - Office Substrate (Copilot, search)
  - `manage` - Office Management API
  - `powerbi` - Power BI
  - `flow` - Power Automate
  - `devops` - Azure DevOps

## Resource shortcuts (v0.3+)

Curated subcommand groups that resolve common flows without typing the full
URL. The verb-first form keeps working - this is purely additive.

```sh
owa-graph                    # top-level help, lists groups
owa-graph mail               # group-level help, lists shortcuts
owa-graph mail list --unread --top 5 --pretty
```

Every shortcut accepts the cross-cutting flags `--pretty`, `--ndjson`, and
`--retry` (the dispatcher peels them off before calling the handler). All
other flags are per-shortcut.

### Scope matrix

The OWA-SPA client `owa-piggy` borrows is FOCI but doesn't carry the full
Graph scope set. The table below is what each group returns against the
default (owa-piggy) auth path on a normal corporate tenant. Anything marked
`needs app-reg` works once you set `GRAPH_APP_CLIENT_ID` for an app
registration that grants the relevant Graph delegated scopes.

| Group       | Default path  | Notes                                   |
|-------------|---------------|-----------------------------------------|
| `me`        | works         | profile, manager, direct reports        |
| `users`     | works         | list / find / get; manager + reports    |
| `teams`     | works         | joined teams, channels, channel msgs    |
| `chats`     | works         | 1:1 + group chats, send messages        |
| `groups`    | works         | M365 groups, members                    |
| `planner`   | works         | Planner tasks, plans, buckets           |
| `files`     | works         | OneDrive list/upload/download/share     |
| `directory` | works         | directory roles, audit logs (admin)     |
| `mail`      | needs app-reg | use `owa-mail` for the Outlook-REST path |
| `calendar`  | needs app-reg | use `owa-cal` for the Outlook-REST path |
| `contacts`  | needs app-reg | personal contacts                       |
| `todo`      | needs app-reg | Microsoft To-Do                         |
| `sites`     | needs app-reg | SharePoint sites and lists              |
| `presence`  | needs app-reg | Teams presence read/set                 |

Auth fallback isn't automatic - if a shortcut returns `403`, switch the
profile to one with `GRAPH_APP_CLIENT_ID` set, or fall through to the
sibling tool (`owa-cal`, `owa-mail`) when the audience-specific path is
the simpler answer.

## Auth

Default path: `owa-graph` shells out to `owa-piggy` for a fresh access
token on every call. `owa-piggy` owns the refresh token; `owa-graph`
stores only an optional profile alias and a default audience in
`~/.config/owa-graph/config`.

App-registration path (broader Graph scopes): set `GRAPH_APP_CLIENT_ID`,
`GRAPH_REFRESH_TOKEN`, and `GRAPH_TENANT_ID` and `owa-graph` will hit the
AAD token endpoint directly with `https://graph.microsoft.com/.default`
scope.

## Scope caveat

The OWA first-party SPA client `owa-piggy` borrows does NOT carry full
Graph permissions: most reads work, calendar/mail/files *writes* via
Graph return `403`. See the [scope matrix](#scope-matrix) above for
which v0.3 shortcuts work on the default path. Set
`GRAPH_APP_CLIENT_ID` to your own app registration to broaden scope,
or use the audience-specific siblings (`owa-cal`, `owa-mail`) which
target the Outlook REST audience instead.

## Scope hint (v0.5+)

Before sending the request, `owa-graph` decodes the JWT's `scp` claim
and matches the request `(path, verb)` against a curated manifest at
`owa_graph/data/scopes.json`. If the scope your call needs isn't in
the token, you get an advisory warning on stderr:

```
$ owa-graph GET /me/contacts
warn: this call requires Contacts.Read; your token does not carry it.
      Likely 403. Set GRAPH_APP_CLIENT_ID for broader scope, or set
      OWA_GRAPH_NO_SCOPE_HINTS=1 to silence this warning.
ERROR: access denied (403). Check permissions/scopes.
```

The warning never blocks the call - it converts an opaque server-side
`403` into an actionable client-side diagnostic. Suppression:

- `OWA_GRAPH_NO_SCOPE_HINTS=1` for CI / scripted use
- `--audience <other>`: hint only fires for `graph` (other audiences
  use different scope namespaces the manifest doesn't cover)
- uncurated paths stay quiet (no false positives)

The manifest is hand-curated and intentionally sparse; see
`owa_graph/data/scopes.json` to extend coverage.

## Shell completion (v0.5+)

Hand-written completion scripts ship under `src/completions/`. No
`argcomplete` dependency.

```sh
# Bash (macOS Homebrew)
ln -s "$(brew --prefix owa-tools)/completions/owa-graph.bash" \
      "$(brew --prefix)/etc/bash_completion.d/owa-graph"

# Zsh (anywhere on $fpath named exactly _owa-graph)
cp src/completions/owa-graph.zsh "$(brew --prefix)/share/zsh/site-functions/_owa-graph"

# Fish
cp src/completions/owa-graph.fish ~/.config/fish/completions/owa-graph.fish
```

Coverage:

- HTTP verbs, resource groups, and reserved subcommands at the top level
- per-group shortcuts after `owa-graph mail <TAB>` etc.
- Graph paths after `owa-graph GET <TAB>` (~10 000 paths from the
  vendored CSDL manifest at `owa_graph/data/paths.json.gz`; `--beta`
  switches to beta paths)
- `--audience <TAB>` lists the 17 known FOCI audiences
- the full flag set is suggested anywhere a flag can appear

The path list itself is dumped by the package (used by the completion
scripts):

```sh
python -m owa_graph.paths           # v1.0 paths, one per line
python -m owa_graph.paths beta      # beta paths
```

The vendored manifest at `owa_graph/data/paths.json.gz` is a committed
artifact regenerated from Graph's CSDL metadata when the schema gains
new paths.

## Development

owa-graph ships in the `owa-tools` suite repository:

```sh
git clone https://github.com/damsleth/owa-tools
cd owa-tools
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

## Machine / agent surface

Every owa binary exposes the same machine surface (see
[agent-integration.md](agent-integration.md) for the full contract):

- `owa-graph schema [<command>]` - JSON command schema (one command if named)
- `owa-graph --help --json` - the same schema via the help flag
- `--agent` - wrap JSON stdout in a stable `{"_owa": ..., "data": ...}`
  envelope (or set `OWA_AGENT=1`)
- `--err-json` - structured JSON errors on stderr (or `OWA_ERR_JSON=1`)
- `--doctor [--json]` - this tool's health / redaction doctor payload

## License

MIT.
