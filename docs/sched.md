# owa-sched

Pipe-friendly scheduling assistant for Outlook / Microsoft 365.
Free/busy lookups and naive multi-attendee slot finding via Graph
`/me/calendar/getSchedule`. Sibling of `owa-cal` / `owa-mail` /
`owa-people`.

JSON on stdout, `--pretty` for humans. Auth is delegated to
[`owa-piggy`](https://github.com/damsleth/owa-piggy).

```
$ owa-sched availability --who alice@x.com,bob@x.com --date tomorrow --pretty
alice@x.com
  2026-05-05 09:00 - 2026-05-05 10:00 [busy] Standup
  2026-05-05 13:00 - 2026-05-05 14:00 [busy] 1:1

bob@x.com
  2026-05-05 11:00 - 2026-05-05 11:30 [tentative] Maybe call

$ owa-sched find-time --who alice@x.com,bob@x.com --duration 30 --week 19 --pretty
Open slots:
  2026-05-04 09:00 - 2026-05-04 09:30
  2026-05-04 14:00 - 2026-05-04 14:30
  ...
```

## Install

```bash
pipx install owa-sched    # once published
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
owa-sched availability --who alice@x.com,bob@x.com --week 19
owa-sched availability --who you@x.com --date tomorrow --pretty

owa-sched find-time --who alice@x.com,bob@x.com --duration 30 --week 19
owa-sched find-time --who you@x.com --date 2026-05-12 --start 09:00 --end 17:00

owa-sched refresh
owa-sched config --profile crayon
```

## Caveats

- The slot finder is naive: it uses a single per-day work-day
  window for everyone, and does not honour each attendee's
  individual `workingHours` from Graph. Good enough for "find me
  half an hour with these two", not a full Outlook scheduling
  assistant replacement.
- Graph's per-attendee error surface (e.g. mailbox not found,
  calendar hidden) is preserved on the JSON output; consult
  `error` field on each attendee.

## License

MIT
