# owa-people

People/contacts CLI for Outlook / Microsoft 365.

Pipe-friendly lookups for people and contacts. Sibling of
[`owa-cal`](cal.md) and [`owa-mail`](mail.md) in the `owa-tools` suite.

```
$ owa-people find "vibeke" --pretty
name              email             title             company
Vibeke Tveit      vtv@example.com   Saksbehandler     Example Org

$ owa-people show vtv@example.com --pretty
Vibeke Tveit
  email:    vtv@example.com
  title:    Saksbehandler
  dept:     Faglig stab
  company:  Example Org
  id:       8a4f...
```

## Install

Part of the `owa-tools` suite — one install gives you all nine binaries plus the `owa-piggy` auth broker:

```bash
brew install damsleth/tap/owa-piggy damsleth/tap/owa-tools
# or: pipx install owa-piggy && pipx install owa-tools
```

Run as `owa-people ...` or via the umbrella `owa people ...`.

## Auth

owa-people shells out to `owa-piggy` for a fresh access token on every call;
`owa-piggy` owns the refresh token and profile registry. Audience: graph.

```bash
owa-piggy setup --profile work        # one-time, opens a browser
```

See [profile-model.md](profile-model.md) for profile precedence.

## Commands

| Command | Summary |
| --- | --- |
| `find <query>` | Search people you've recently interacted with (relevance-ranked: `/me/people`). |
| `show <id-or-email>` | Show full details for one person (`/users/<id>`). |
| `directory <query>` | Search the company directory (`/users`). |
| `me` | Show the authenticated user (`/me`). |
| `manager [<id-or-email>]` | Show a user's manager (`/users/<id>/manager`; default: you). |
| `direct-reports [<id-or-email>]` | List a user's direct reports (`/directReports`). |
| `org-chart [<id-or-email>]` | Walk managers up and direct reports down. |
| `photo [<id-or-email>]` | Fetch a user's photo (`/photo/$value`) — binary on stdout. |
| `groups [<id-or-email>]` | List a user's group memberships (`/memberOf`). |
| `contacts` | List your personal contacts (`/me/contacts`). |
| `contact-create` | Create a personal contact (`POST /me/contacts`). |
| `contact-update <contact-id>` | Update a personal contact (`PATCH`). |
| `contact-delete <contact-id>` | Delete a personal contact (`DELETE`; confirms unless `--confirm`). |
| `refresh` | Force a token refresh and verify auth. |
| `config` | View or update configuration. |

`find`, `show`, and `directory` take a positional argument (`<query>` or
`<id-or-email>`). A bare first token is shorthand for `find`, so
`owa-people "ada"` is the same as `owa-people find "ada"`.

`manager`, `direct-reports`, `org-chart`, `photo`, and `groups` take an
optional positional id-or-email and default to the authenticated user when
omitted. `org-chart` accepts `--depth <n>` (manager levels to climb, default
1, cap 3). `photo` writes raw image bytes to stdout (redirect to a file) or
to `--out <path>`.

Add `--pretty` for a table; `--profile <alias>` to switch profiles for one
invocation. `--limit <n>` (alias `--top <n>`) bounds the page size (default
25 — 50 for `contacts`/`groups` — cap 100). `contacts` also accepts
`--search <term>`. The list commands (`find`, `directory`, `contacts`) accept
`--select <props>` and `--filter <expr>` as OData passthrough.

`directory`, `contacts`, `direct-reports`, and `groups` return a single page
by default. Pass `--all` to follow `@odata.nextLink` until the collection is
exhausted; `--limit` still controls the page size requested per round-trip.
(`show`, `me`, and `manager` return a single object and have no `--all`.
`find` hits `/me/people`, which is relevance-ranked and does not page, so it
has no `--all` either — raise `--limit` to widen the result set.)

Contact mutations follow the suite convention: `contact-create` and
`contact-update` take field flags (`--name`, `--given`, `--surname`,
`--email`, `--mobile`, `--company`, `--title`); `contact-delete` confirms
interactively unless `--confirm` is passed and refuses to run
non-interactively without it.

```bash
owa-people find "vibeke" --pretty
owa-people show vtv@example.com
owa-people directory "norconsult" --limit 50 --pretty
owa-people directory "norconsult" --all | jq length
owa-people directory "ada" --select "id,displayName,mail" --filter "department eq 'IT'"
owa-people me --pretty
owa-people manager vtv@example.com --pretty
owa-people direct-reports --all --pretty
owa-people org-chart vtv@example.com --depth 2 --pretty
owa-people photo vtv@example.com --out avatar.jpg
owa-people groups --pretty
owa-people contacts --all --pretty
owa-people contact-create --name "Ada Lovelace" --email ada@example.com --company "Analytical Engines"
owa-people contact-update AAMk... --title "Countess"
owa-people contact-delete AAMk... --confirm
owa-people --profile crayon find "ole kristian"
owa-people refresh
owa-people config --profile work
```

## Output contract

JSON on stdout by default; diagnostics/prompts/errors on stderr. `--pretty` is
the human-readable opt-in. Exit codes follow the suite taxonomy (see
[security.md](security.md) and [agent-integration.md](agent-integration.md)).

## Machine / agent surface

Every owa binary exposes the same machine surface:

- `owa-people schema [<command>]` — JSON command schema (one command if named)
- `owa-people --help --json` — same schema via the help flag
- `--agent` — wrap JSON stdout in a stable `{"_owa": ..., "data": ...}` envelope (or `OWA_AGENT=1`)
- `--err-json` — structured JSON errors on stderr (or `OWA_ERR_JSON=1`)
- `--doctor [--json]` — this tool's health / redaction doctor payload

See [agent-integration.md](agent-integration.md) for the full contract.

## Caveats

- `find` queries `/me/people`, which is relevance-ranked and does not return
  `@odata.nextLink`. It has no `--all`; raise `--limit` to widen results.
- `directory` searches the company directory (`/users`) and depends on the
  tenant exposing directory data to your account.
