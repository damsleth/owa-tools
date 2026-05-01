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
Graph permissions. Calls like `GET /me`, `/users`, `/me/joinedTeams`,
and most directory queries work; calendar/mail/files writes via Graph
return 403. Set `GRAPH_APP_CLIENT_ID` to your own app registration to
broaden scope, or use the audience-specific siblings (`owa-cal`,
`owa-mail`) which target the Outlook REST audience instead.

## Development

```sh
pip install -e '.[test]'
pytest -q
python -m compileall owa_graph
```

## License

MIT.
