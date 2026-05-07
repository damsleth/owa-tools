# AGENTS.md

Instructions for AI coding agents working in this repo.

## What this is

`owa-people` is a stdlib-only Python CLI for looking up people and
contacts in Outlook / Microsoft 365 from the terminal. JSON on
stdout, logs on stderr, `--pretty` for humans.

Sibling of `owa-cal`/`owa-mail`; same auth model (delegated to
`owa-piggy` on PATH) and same coding style. Backend is **Microsoft
Graph** - this differs from `owa-cal`/`owa-mail`, which use the
Outlook REST audience. The Graph audience is correct here because
`/me/people`, `/users`, and `/me/contacts` are Graph-native; the
OWA SPA scopes that owa-piggy borrows do carry the relevant
permissions for read.

## Ground rules

- **Stdlib only** at runtime. No `requests`, no deps. `pytest` is
  dev-only.
- **JSON on stdout, logs on stderr.** Callers pipe to `jq`. Don't
  decorate the JSON path.
- **Never commit real tokens, real tenant IDs, or actual
  `~/.config/owa-people/config` contents** in tests or fixtures.
- **Audience is `graph`, not `outlook`.** Don't change `auth.py` to
  request Outlook tokens - this tool's endpoints are all Graph.
- **Don't add write commands speculatively.** Adding/editing
  contacts is plausible but unbuilt; the "find/show/directory"
  read surface is what the user asked for. If you add writes,
  they go through Graph `/me/contacts` and need explicit
  user-facing guard rails (no bulk modify without confirmation).

## Layout

```
owa_people/
  __init__.py     # re-exports `main`
  __main__.py     # `python -m owa_people`
  cli.py          # arg parsing + dispatch + cmd_* handlers
  auth.py         # do_token_refresh + setup_auth (owa-piggy bridge, audience=graph)
  api.py          # Graph HTTP helper (urllib)
  config.py       # CONFIG_PATH, load_config, save_config, config_set
  people.py       # normalize_person — projects /me/people, /users,
                  # /me/contacts into one flat shape
  format.py       # --pretty rendering
  jwt.py          # token_minutes_remaining (no signature validation)
tests/            # pytest suite, no network
pyproject.toml
```

## Working on this repo

- Each new subcommand is a `cmd_*` function in `cli.py` that parses
  its own flags. Match the existing flat dispatch style.
- All read endpoints go through `api.api_get` and feed
  `normalize_person`. Don't surface raw Graph shapes - the flat
  shape is the contract.
- Search-style endpoints need `ConsistencyLevel: eventual`.
  `api_request` accepts `extra_headers` for that.

## Verification before claiming done

- `python -m compileall -q owa_people` passes.
- `python -m owa_people --help` runs without traceback on a clean
  machine.
- `pytest -q` is green.
- If you touched the people/directory path, run against a real
  profile: `owa-people find "someone you know" --pretty` and
  `owa-people directory "yourcompany" --pretty`. If you cannot
  run against a real profile, say so explicitly.

## What NOT to do

- Don't switch the audience to Outlook - the Outlook REST API does
  not expose people/users/contacts in a useful shape.
- Don't pre-resolve `--profile` aliases against any local profile
  file (owa-people has no webcal-style local source). Forwarding to
  owa-piggy is the only path.
- Don't add telemetry, crash reporting, or update checks.
