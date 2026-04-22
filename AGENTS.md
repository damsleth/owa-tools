# AGENTS.md

Instructions for AI coding agents working in this repo.

## What this is

`cal-cli` is a small stdlib-only Python CLI (package at `cal_cli/`,
~900 lines split across a handful of modules) for reading and writing
Microsoft 365 / Outlook calendar events from the terminal. JSON on
stdout, logs on stderr, `--pretty` for humans.

The tool is a sibling of [`owa-piggy`](../owa-piggy) and shares its
layout and coding style. Default auth path: shell out to `owa-piggy`
on `$PATH` (treat them as two POSIX utils piped together); owa-piggy
owns the refresh token, cal-cli stores only an optional profile alias
(`owa_piggy_profile`). Alternative path: set `OUTLOOK_APP_CLIENT_ID`
(plus `OUTLOOK_REFRESH_TOKEN` / `OUTLOOK_TENANT_ID` in the config
file) to use a user-owned app registration directly.

## Ground rules

- **Stdlib only** at runtime. No `requests`, no `msal`, no deps.
  `pytest` is dev-only under `[project.optional-dependencies] test`.
- **JSON on stdout, logs on stderr.** Callers pipe `cal-cli events`
  into `jq`. Do not print progress, timing, or decorations to stdout.
- **Never commit real refresh tokens, access tokens, tenant IDs, or
  `~/.config/cal-cli/config` contents**, even in tests or fixtures.
  Use obvious fakes (`"fake-rt-for-tests"`). Refresh-token handling
  applies only on the app-registration path; on the owa-piggy path
  cal-cli holds no secrets.
- **Preserve the "only provided fields" invariant in
  `build_patch_json`**. Adding keys with empty values silently clobbers
  other event fields in Outlook.
- **Do not change `default_timezone` to IANA** (e.g. `Europe/Oslo`).
  The Outlook REST API wants the Windows zone name
  (`W. Europe Standard Time`); IANA breaks the create/update flow.
- **Do not switch the backend to Microsoft Graph on the owa-piggy
  auth path.** OWA's first-party SPA client (which owa-piggy borrows)
  does not carry `Calendars.ReadWrite` or `MailboxSettings.*` on the
  Graph audience - only on the Outlook audience. Switching `api_base`
  to `graph.microsoft.com/v1.0` returns 403 on every call. See
  `cal_cli/auth.py` docstring for the scope decode. Graph is an
  option only for users with their own `OUTLOOK_APP_CLIENT_ID`.

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
  api.py             # Outlook REST HTTP helper (urllib)
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

## Cutting a release (only when the user asks)

Releases are pushed out through a Homebrew tap at
`~/Code/homebrew-tap` (`damsleth/homebrew-tap` on GitHub). The
formula pins a specific tag tarball and sha256, so a version bump
here must be followed by a tap update or `brew upgrade` stays on
the old version.

When the user says "cut a release" / "new patch version" / "ship it":

1. Pick the bump. Patch (`0.3.0 -> 0.3.1`) for bug fixes, doc
   corrections, small UX polish. Minor (`0.3.0 -> 0.4.0`) for new
   flags, new behaviors, anything a user might notice. Never bump
   major without explicit instruction - this tool is 0.x by design.
2. Commit the feature work separately from the version bump. Keep
   one `Bump version to X.Y.Z` commit sitting on top of the feature
   commit so `git log` reads cleanly.
3. Update `pyproject.toml` `version = "X.Y.Z"`. No other file tracks
   the version today.
4. Push `main`, then `git tag vX.Y.Z && git push origin vX.Y.Z`.
   Never retag a version that's already public - Homebrew users
   cache the tarball by sha.
5. Fetch the GitHub-generated tarball and compute its sha256:
   `curl -sL https://github.com/damsleth/cal-cli/archive/refs/tags/vX.Y.Z.tar.gz -o /tmp/cal-cli-X.Y.Z.tar.gz && shasum -a 256 /tmp/cal-cli-X.Y.Z.tar.gz`
6. Edit `~/Code/homebrew-tap/Formula/cal-cli.rb` - bump the `url`
   tag and the `sha256`. Nothing else changes unless dependencies
   did.
7. Commit the tap with message `cal-cli X.Y.Z` (matches the tap's
   existing convention) and push.

If any step fails midway (tag push rejected, sha mismatch, tap push
rejected), stop and surface the error - do not try to "fix" a
published tag by force-pushing.

## What NOT to do

- Don't register an Azure AD app "just to make auth simpler" - that is
  what `owa-piggy` exists to avoid. The app-registration path is
  optional for users who already have one.
- Don't add telemetry, crash reporting, update checks, or any network
  call beyond the Outlook REST API and `login.microsoftonline.com`.
- Don't add emoji, badges, or marketing copy to docs.
- Don't break the `jq`-friendly JSON output contract on stdout.
