# owa-people

Pipe-friendly CLI for looking up people and contacts in Outlook /
Microsoft 365. Sibling of [`owa-cal`](https://github.com/damsleth/owa-cal)
and [`owa-mail`](https://github.com/damsleth/owa-mail).

JSON on stdout, `--pretty` for humans. Auth is delegated to
[`owa-piggy`](https://github.com/damsleth/owa-piggy).

```
$ owa-people find "vibeke" --pretty
name              email           title             company
Vibeke Tveit      vtv@une.no      Saksbehandler     UNE

$ owa-people show vtv@une.no --pretty
Vibeke Tveit
  email:    vtv@une.no
  title:    Saksbehandler
  dept:     Faglig stab
  company:  UNE
  id:       8a4f...
```

## Install

```bash
pipx install owa-people    # once published
# or, from a clone:
pipx install .
```

Then ensure `owa-piggy` is set up:

```bash
brew install damsleth/tap/owa-piggy
owa-piggy setup --profile work --email you@example.com
```

## Commands

```bash
owa-people find <query>          # /me/people - relevance-ranked colleagues
owa-people show <id-or-email>    # /users/<id> - one person, full details
owa-people directory <query>     # /users - company directory search
owa-people me                    # /me - the authenticated user
owa-people contacts              # /me/contacts - personal contacts
owa-people refresh               # force a token refresh, verify auth
owa-people config --profile X    # pin a default owa-piggy profile
```

Add `--pretty` for a table; `--limit N` to bound the page size (default
25, max 100); `--profile <alias>` to switch profiles for one
invocation.

`directory` and `contacts` return a single page by default. Pass
`--all` to follow `@odata.nextLink` until the collection is exhausted;
`--limit` still controls the page size requested per round-trip.
(`show` and `me` return a single object and have no `--all`. `find`
hits `/me/people`, which is relevance-ranked and does not return
`@odata.nextLink`, so it has no `--all` either — raise `--limit` to
widen the result set.)

```bash
owa-people directory "norconsult" --all | jq length
owa-people contacts --all --pretty
```

## Auth

`owa-people` shells out to `owa-piggy` on every call to mint a fresh
Graph access token. Profile selection mirrors the rest of the suite:
`--profile <alias>` overrides `owa_piggy_profile` in the config file.

## License

MIT
