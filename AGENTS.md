# AGENTS.md

Instructions for AI coding agents working in this repo.

## What this is

`cal-cli` is a small stdlib-only Python CLI (package at `cal_cli/`,
~900 lines split across a handful of modules) for reading and writing
Microsoft 365 / Outlook calendar events from the terminal. JSON on
stdout, logs on stderr, `--pretty` for humans.

The tool is a sibling of [`owa-piggy`](../owa-piggy) and shares its
layout and coding style. For auth it shells out to the `owa-piggy`
binary on `$PATH` (treat them as two POSIX utils piped together) OR
uses an optional app-registration `client_id` if the user provides one
via `OUTLOOK_APP_CLIENT_ID`.

## Ground rules

- **Stdlib only** at runtime. No `requests`, no `msal`, no deps.
  `pytest` is dev-only under `[project.optional-dependencies] test`.
- **JSON on stdout, logs on stderr.** Callers pipe `cal-cli events`
  into `jq`. Do not print progress, timing, or decorations to stdout.
- **Never commit real refresh tokens, access tokens, tenant IDs, or
  `~/.config/cal-cli/config` contents**, even in tests or fixtures.
  Use obvious fakes (`"fake-rt-for-tests"`).
- **Preserve the "only provided fields" invariant in
  `build_patch_json`**. Adding keys with empty values silently clobbers
  other event fields in Outlook.
- **Do not change `default_timezone` to IANA** (e.g. `Europe/Oslo`).
  The Outlook REST API wants the Windows zone name
  (`W. Europe Standard Time`); IANA breaks the create/update flow.

## Layout

```
cal_cli/
  __init__.py        # re-exports `main` so `cal-cli = "cal_cli:main"` resolves
  __main__.py        # `python -m cal_cli`
  cli.py             # arg parsing + dispatch + cmd_* handlers
  config.py          # CONFIG_PATH, load_config, save_config, config_set
  dates.py           # today/tomorrow/yesterday, resolve_date, iso_week_range
  events.py          # normalize_event, build_event_json, build_patch_json
  format.py          # --pretty formatter
  auth.py            # do_token_refresh (app-reg path + owa-piggy bridge)
  api.py             # Outlook REST / Graph HTTP helper (urllib)
  jwt.py             # token_minutes_remaining (no signature validation)
scripts/
  add-to-path.sh     # pipx-based installer shim
tests/               # pytest suite around pure functions + CLI smoke
Formula/cal-cli.rb   # Homebrew tap formula
pyproject.toml
README.md
SECURITY.md
```

## Working on this repo

- **Read before editing.** Don't change code you haven't read.
- **Preserve behavior** unless a commit explicitly changes it. Recent
  commits encode subtle decisions: post-create duplicate check,
  env-wins-over-config precedence, atomic config writes with 0600
  perms, unknown-command check before auth. Do not regress those.
- **Don't add abstractions.** A `class CalendarClient` wrapping three
  `urlopen` calls is noise. Flat functions are the norm.
- **Test what matters.** Pure functions (`resolve_date`,
  `iso_week_range`, `make_datetime`, `parse_kv_stream`,
  `load_config`/`save_config`, `normalize_event`, `build_event_json`,
  `build_patch_json`, `format_events_pretty`) plus CLI dispatch are
  the test targets. Network calls and interactive prompts are not.

## Verification before claiming done

- `python -m compileall -q cal_cli` passes.
- `python -m cal_cli --help` runs without traceback on a machine with
  no config.
- `pytest -q` is green.
- If you touched the event read/write path: `cal-cli events --pretty`
  and `cal-cli create --subject test --date tomorrow --start 09:00
  --end 09:30` still work against a real configured profile. If you
  cannot run against a real profile, say so explicitly rather than
  claiming it works.

## Commits and PRs

- Short imperative commit messages (see `git log`). One line is
  usually enough; expand in the body only when the *why* isn't
  obvious from the diff.
- One logical change per commit.
- Do not push or open PRs without the user asking. Do not force-push
  `main`.

## What NOT to do

- Don't register an Azure AD app "just to make auth simpler" - that is
  what `owa-piggy` exists to avoid. The app-registration path is
  optional for users who already have one.
- Don't add telemetry, crash reporting, update checks, or any network
  call beyond the Outlook REST API and `login.microsoftonline.com`.
- Don't swap to Graph casing as the default without a clear reason.
  Outlook REST is what the refresh token lands on; Graph works but
  adds a round-trip for no practical gain right now.
- Don't add emoji, badges, or marketing copy to docs.
- Don't break the `jq`-friendly JSON output contract on stdout.
