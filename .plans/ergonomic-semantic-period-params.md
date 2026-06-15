# Ergonomic & semantic period parameters for owa-tools

_Created 2026-06-15_

## Goal

Make time-relative period selection ergonomic across the owa CLIs, starting
with `owa-cal events`. Today you must know an absolute ISO week number or type
a full `--from/--to` range. We want natural relative values:

```
owa-cal events --week last      # previous ISO week
owa-cal events --week -1        # same as last
owa-cal events --week next      # next ISO week
owa-cal events --week +1        # same as next
owa-cal events --week current   # this week (explicit form of default)
owa-cal events --month          # this calendar month (new period flag)
owa-cal events --month next     # next month
owa-cal events --month -2       # two months ago
owa-cal events --year +1        # next year
```

`--month` defaults to `current`. `--week` and `--year` gain the same
`current | last | next | +n | -n` vocabulary. The numeric forms still work
(`--week 16`, `--year 2026`) and keep their current meaning.

## Decisions (locked 2026-06-15)

1. **Resolver lives in `owa_core/periods.py`**, shared by owa-cal + owa-sched.
2. **`--year` unsigned `>= 100` is an absolute year**; relative requires a sign
   (`+1`/`-1`) or keyword (`current/last/next`).
3. **Conflicting period flags hard-error** (usage error naming both flags).
4. **`--date` relative sugar is IN this pass**: day offsets (`--date +1`,
   `--date -3`) and weekday names (`monday`…`sunday`, resolving to the *next*
   occurrence; document the direction). Keep `today/tomorrow/yesterday`.

## Scope decision (resolved → shared core)

The same `--date/--from/--to/--week/--year` flags exist in **two** tools today:

- `owa-cal events` — `src/owa_cal/cli.py:320` (`_resolve_event_window` at :246)
- `owa-sched` — `src/owa_sched/cli.py:177` and `:235` (duplicated block)

Each tool also carries its own `dates.py` with duplicated
`today/tomorrow/yesterday/iso_week_range` helpers
(`src/owa_cal/dates.py`, `src/owa_sched/dates.py`, `src/owa_mail/dates.py`).

`owa-mail` uses `--from` for **sender** and `--since`/`--to` for dates —
different semantics, so it is out of scope for the period vocabulary (though
`--since` could later accept relative day offsets).

**Recommendation:** put the relative-period resolver in `owa_core` (new
`owa_core/periods.py`) so cal + sched share one implementation and one set of
tests, rather than copy-pasting parsing into each `dates.py`. Matches the
AGENTS.md "single source of truth" rule. The smaller alternative (owa-cal only)
re-introduces drift between two tools that already share the flag surface.

## Design

New module `src/owa_core/periods.py`:

- `resolve_week(value, *, today=None) -> (year, week)` — accepts
  `int | "current"/"this" | "last"/"prev"/"previous" | "next" | "+n" | "-n"`.
  Relative values computed against the current ISO week, rolling the year at
  week 1 / week 52-53 boundaries (use `date.isocalendar()` + `timedelta(weeks=n)`,
  not naive arithmetic).
- `resolve_month(value, *, today=None) -> (year, month)` — same vocabulary,
  month arithmetic with year rollover.
- `resolve_year(value, *, today=None) -> int` — `int | current | +n | -n`.
- `month_range(year, month) -> (from_iso, to_iso)` — first to last day.
- `resolve_day(value, *, today=None) -> iso` — extends today/tomorrow/yesterday
  with signed offsets (`+1`/`-3`) and weekday names (`monday`…`sunday`). A bare
  weekday name resolves to that day **in the current ISO week** (Mon-anchored,
  so it can be in the past — e.g. on a Wednesday, `--date monday` is two days
  ago). A trailing signed week offset shifts by whole weeks:
  `monday+1` = next week's Monday, `friday-2` = the Friday two weeks back.
  Grammar: `<weekday>[(+|-)<n>]`. This keeps `--date` self-contained (no need to
  pair with `--week`, so no conflict with decision 3). Supersedes owa-cal's
  `resolve_date`.
- Move the canonical `iso_week_range(week, year)` here; have tool `dates.py`
  re-export, or update call sites.

Parsing rules (shared helper `parse_relative(value, keywords)`):
- Distinguish absolute vs relative by leading sign: `--week 16` = week 16;
  `--week +1` = next week; `--week -1` = last week.
- `--year`: treat unsigned `>= 100` as an absolute year; require an explicit
  sign for relative (`+1`/`-1`). Document clearly.
- keyword aliases: `current`/`this`, `last`/`prev`/`previous`, `next`.

## Wiring

`owa-cal events` (`src/owa_cal/cli.py`):
1. Change `--week`/`--year` parsing from `_require_int` to `_require_value`
   (keep raw string; resolve later).
2. Add `--month` flag (string value, default unset).
3. Extend `_resolve_event_window(...)` with precedence:
   explicit `--from/--to` > `--date` > `--week` > `--month` > `--year` > today.
   Hard-error on conflicting period flags (e.g. `--week` + `--month`) rather
   than silently picking one.
4. `cmd_events_webcal` shares `_resolve_event_window`, so most of this is free —
   verify.

`owa-sched` (`src/owa_sched/cli.py:177`, `:235`): apply identical resolver
calls. Factor the shared window resolution if the two blocks are truly identical.

## Help / completions / docs

- Update `print_help()` Events block (`cli.py:140`) and `_EVENTS_FLAGS` schema
  summaries (`cli.py:747`). Add `--month`.
- Shell completions `src/completions/owa-cal.{bash,fish,zsh}` — add `--month`,
  suggest `current/last/next` as candidates for `--week/--month/--year`.
- owa-sched help + completions to match.
- `docs/` and `CHANGELOG.md`.
- cj-owa-tools skill reference — check if it needs a period-flag note.

## Tests

- `src/tests/core/test_periods.py` (new) — table-driven: every keyword +
  signed/unsigned form for week/month/year, including rollover edges
  (week 1 `-1` → prior year's last week; Dec `+1` → Jan next year; ISO week-53
  years), plus `resolve_day` offsets and weekday-name resolution. Inject
  `today=` so tests are deterministic (matches dates.py style).
- Extend `src/tests/cal/test_dates.py` / `test_cli_validation.py` for new flag
  parsing + precedence/conflict errors. Same for sched.
- **Coverage gate is 90% with ~0 slack** (memory: owa-tools-release-gotchas) —
  run `pytest --cov` before declaring done.

## Resolved: reaching another week's weekday

`--date <weekday>±<n>` shifts by whole weeks: `monday+1` = next week's Monday,
`friday-2` = Friday two weeks back. Self-contained on `--date`, so no `--week`
pairing and no conflict with decision 3. Test the boundary cases (week/year
rollover via the offset).

## Out of scope (for now)

- owa-mail relative `--since` values (different flag semantics).
- Natural-language ranges ("this quarter", "ytd").
