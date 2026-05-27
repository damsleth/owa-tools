# owa-sched

Scheduling assistant for Outlook / Microsoft 365.

Free/busy lookups and naive multi-attendee slot finding via Graph
`/me/calendar/getSchedule`. Sibling of `owa-cal` / `owa-mail` / `owa-people`.

```
$ owa-sched availability --who alice@example.com,bob@example.com --date tomorrow --pretty
alice@example.com
  2026-05-05 09:00 - 2026-05-05 10:00 [busy] Standup
  2026-05-05 13:00 - 2026-05-05 14:00 [busy] 1:1

bob@example.com
  2026-05-05 11:00 - 2026-05-05 11:30 [tentative] Maybe call

$ owa-sched find-time --who alice@example.com,bob@example.com --duration 30 --week 19 --pretty
Open slots:
  2026-05-04 09:00 - 2026-05-04 09:30
  2026-05-04 14:00 - 2026-05-04 14:30
  ...
```

## Install

Part of the `owa-tools` suite — one install gives you all nine binaries plus the `owa-piggy` auth broker:

```bash
brew install damsleth/tap/owa-piggy damsleth/tap/owa-tools
# or: pipx install owa-piggy && pipx install owa-tools
```

Run as `owa-sched ...` or via the umbrella `owa sched ...`.

## Auth

owa-sched shells out to `owa-piggy` for a fresh access token on every call;
`owa-piggy` owns the refresh token and profile registry. Audience: graph.

```bash
owa-piggy setup --profile work        # one-time, opens a browser
```

See [profile-model.md](profile-model.md) for profile precedence.

## Commands

| Command | Summary |
| --- | --- |
| `availability` | List attendee free/busy windows. |
| `find-time` | Find open slots when every attendee is free. |
| `refresh` | Force a token refresh and verify auth. |
| `config` | View or update configuration. |

`availability` and `find-time` both require `--who <addr[,addr]>` (a
comma-separated list of attendee emails) and accept the same window selectors:
`--date <date>` (a single day, also `today` / `tomorrow` / `yesterday`),
`--from` / `--to` for a range, or `--week <n>` (with optional `--year <n>`).
`--start` / `--end` set the work-day window (defaults 08:00 / 17:00, or the
`default_work_start` / `default_work_end` config values).

- `availability` adds `--interval <min>` (availabilityView granularity,
  default 30).
- `find-time` adds `--duration <min>` (slot length, default 30).
- `--profile <alias>` forwards to `owa-piggy` for one invocation.

```bash
owa-sched availability --who alice@example.com,bob@example.com --week 19
owa-sched availability --who you@example.com --date tomorrow --pretty

owa-sched find-time --who alice@example.com,bob@example.com --duration 30 --week 19
owa-sched find-time --who you@example.com --date 2026-05-12 --start 09:00 --end 17:00

owa-sched refresh
owa-sched config --profile crayon
```

## Output contract

JSON on stdout by default; diagnostics/prompts/errors on stderr. `--pretty` is
the human-readable opt-in. Exit codes follow the suite taxonomy (see
[security.md](security.md) and [agent-integration.md](agent-integration.md)).

## Machine / agent surface

Every owa binary exposes the same machine surface:

- `owa-sched schema [<command>]` — JSON command schema (one command if named)
- `owa-sched --help --json` — same schema via the help flag
- `--agent` — wrap JSON stdout in a stable `{"_owa": ..., "data": ...}` envelope (or `OWA_AGENT=1`)
- `--err-json` — structured JSON errors on stderr (or `OWA_ERR_JSON=1`)
- `--doctor [--json]` — this tool's health / redaction doctor payload

See [agent-integration.md](agent-integration.md) for the full contract.

## Caveats

- The slot finder is naive: it uses a single per-day work-day window for
  everyone, and does not honour each attendee's individual `workingHours` from
  Graph. Good enough for "find me half an hour with these two", not a full
  Outlook scheduling assistant replacement.
- Graph's per-attendee error surface (e.g. mailbox not found, calendar hidden)
  is preserved on the JSON output; consult the `error` field on each attendee.
