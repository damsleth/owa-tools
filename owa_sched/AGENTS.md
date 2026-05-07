# AGENTS.md

Instructions for AI coding agents working in this repo.

## What this is

`owa-sched` is a stdlib-only Python CLI for free/busy lookup and
naive multi-attendee slot finding against Outlook / Microsoft 365.
JSON on stdout, logs on stderr, `--pretty` for humans.

Backend is **Microsoft Graph** (`POST /me/calendar/getSchedule`),
not the Outlook REST audience that owa-cal uses. The endpoint is
Graph-only and the OWA SPA scopes carry `Calendars.Read.Shared`,
which is what's needed.

## Ground rules

- **Stdlib only** at runtime.
- **JSON on stdout, logs on stderr.** Never decorate the JSON path.
- **Never commit real tenant data.** Use obvious fakes in tests
  (`alice@x.com`, `bob@x.com`).
- **Audience is `graph`.** Outlook REST has no equivalent of
  `getSchedule`.
- **Slot finder is naive.** It assumes per-day work-day boundaries
  and equal-length slots; it does NOT honour each attendee's
  individual `workingHours` from Graph. Don't pretend it does.
  When you upgrade it, read `workingHours` and intersect with the
  window per attendee.
- **Half-open intervals.** Touching at a boundary is not overlap;
  see `dates.overlaps`. Tests pin this.

## Layout

```
owa_sched/
  __init__.py     # re-exports `main`
  __main__.py     # `python -m owa_sched`
  cli.py          # arg parsing + dispatch + cmd_* handlers
  auth.py         # owa-piggy bridge, audience=graph
  api.py          # Graph HTTP helper (urllib)
  config.py       # CONFIG_PATH, load/save, default work-day window
  dates.py        # date arithmetic, ISO week, slot generators (pure)
  schedule.py     # normalize_attendee, find_open_slots (pure)
  format.py       # --pretty rendering
  jwt.py          # token_minutes_remaining (no signature validation)
tests/            # pytest suite, no network
pyproject.toml
```

## Working on this repo

- Each new subcommand is a `cmd_*` function in `cli.py`. Match the
  flat dispatch style.
- Anything time-zone-aware should go through Graph's
  `dateTime + timeZone` shape, not local offset strings.
- `find_open_slots` must remain pure - all I/O happens before it
  is called. The CLI translates the Graph response into the dicts
  it expects.

## Verification before claiming done

- `python -m compileall -q owa_sched` passes.
- `python -m owa_sched --help` runs without traceback on a clean
  machine.
- `pytest -q` is green.
- If you touched the schedule path: `owa-sched availability --who
  <email> --pretty` and `owa-sched find-time --who <email>
  --duration 30 --pretty` against a real profile. If you cannot
  run against a real profile, say so explicitly.

## What NOT to do

- Don't switch the audience to Outlook.
- Don't add per-attendee delegate auth. The tool runs as the
  authenticated user; if the target's calendar is hidden, Graph
  returns a per-entry error and we surface that. Don't pretend to
  resolve it.
- Don't add timezone math beyond `make_local_iso` /
  `parse_local_iso`. Graph carries timezone state on every payload;
  re-implementing it client-side will drift.
