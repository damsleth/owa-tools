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
| `contacts` | List your personal contacts (`/me/contacts`). |
| `refresh` | Force a token refresh and verify auth. |
| `config` | View or update configuration. |

`find`, `show`, and `directory` take a positional argument (`<query>` or
`<id-or-email>`). A bare first token is shorthand for `find`, so
`owa-people "ada"` is the same as `owa-people find "ada"`.

Add `--pretty` for a table; `--profile <alias>` to switch profiles for one
invocation. `--limit <n>` bounds the page size (default 25 — 50 for
`contacts` — cap 100). `contacts` also accepts `--search <term>`.

`directory` and `contacts` return a single page by default. Pass `--all` to
follow `@odata.nextLink` until the collection is exhausted; `--limit` still
controls the page size requested per round-trip. (`show` and `me` return a
single object and have no `--all`. `find` hits `/me/people`, which is
relevance-ranked and does not page, so it has no `--all` either — raise
`--limit` to widen the result set.)

```bash
owa-people find "vibeke" --pretty
owa-people show vtv@example.com
owa-people directory "norconsult" --limit 50 --pretty
owa-people directory "norconsult" --all | jq length
owa-people me --pretty
owa-people contacts --all --pretty
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
