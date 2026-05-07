# owa-graph

Pipe-friendly Microsoft Graph CLI. One-off Graph queries with `owa-piggy`
auth, no token plumbing, no `az login`, no app registration required.

```sh
owa-graph GET /me
owa-graph GET '/users?$top=5' --pretty
owa-graph GET /users --all --ndjson | jq -c .displayName
owa-graph GET /users --search 'displayName:Bob' --count
owa-graph GET /me/messages --top 10 --select id,subject,from
owa-graph POST /me/sendMail --body @mail.json
owa-graph PATCH /me/messages/AAMk... --body '{"isRead":true}'
owa-graph GET /me/drive/root/children --beta
owa-graph GET /me --curl | pbcopy
owa-graph GET me/events --audience outlook --pretty
owa-graph batch requests.json --pretty
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

```sh
brew install damsleth/tap/owa-piggy   # auth broker, required
pip install owa-graph                 # or: uvx owa-graph GET /me
```

## How it works

`owa-graph` is a thin verb-first wrapper around Microsoft Graph that
delegates auth to [`owa-piggy`](https://github.com/damsleth/owa-piggy):
on every call it shells out to `owa-piggy token --audience graph
--json`, takes the access token from stdout, and issues the HTTP
request with the right base URL and Bearer header.

- JSON on stdout, logs on stderr.
- `--pretty` prints tables for users / messages / drive items, indented
  JSON for everything else.
- `--curl` and `--az` print the equivalent shell command instead of
  executing - useful for sharing, scripting, or piping into `pbcopy`.
- `--all` follows `@odata.nextLink` until exhausted; pair with
  `--ndjson` to stream items one per line through `jq`.
- `--count` and `--search` set Graph's `ConsistencyLevel: eventual`
  header so advanced directory queries don't 400.
- `--retry` honors `Retry-After` once on 429/503 (capped at 60s).
- `owa-graph batch <file|->` posts a JSON-batching request to `/$batch`;
  flat arrays are auto-wrapped in `{"requests": [...]}`.
- `--beta` switches to `https://graph.microsoft.com/beta`.
- `--audience` retargets at any FOCI audience `owa-piggy` knows about
  (Outlook REST, Teams, Azure Mgmt, KeyVault, etc.) using the same
  query ergonomics.

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

Hand-written completion scripts ship under `completions/`. No
`argcomplete` dependency.

```sh
# Bash (macOS Homebrew)
ln -s "$(brew --prefix owa-graph)/completions/owa-graph.bash" \
      "$(brew --prefix)/etc/bash_completion.d/owa-graph"

# Zsh (anywhere on $fpath named exactly _owa-graph)
cp completions/owa-graph.zsh "$(brew --prefix)/share/zsh/site-functions/_owa-graph"

# Fish
cp completions/owa-graph.fish ~/.config/fish/completions/owa-graph.fish
```

Coverage:

- HTTP verbs, resource groups, and reserved subcommands at the top level
- per-group shortcuts after `owa-graph mail <TAB>` etc.
- Graph paths after `owa-graph GET <TAB>` (~10 000 paths from the
  vendored CSDL manifest at `owa_graph/data/paths.json.gz`; `--beta`
  switches to beta paths)
- `--audience <TAB>` lists the 13 known FOCI audiences
- the full flag set is suggested anywhere a flag can appear

Refresh the path manifest:

```sh
python3 scripts/refresh-paths.py     # writes owa_graph/data/paths.json.gz
```

Run periodically (and pinned in CI) to track Graph schema additions.

## Development

```sh
pip install -e '.[test]'
pytest -q
python -m compileall owa_graph
```

## License

MIT.
