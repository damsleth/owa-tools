# owa-sched-findmeetingtimes

_Created 2026-06-23_

## Goal

Give owa-sched real server-side meeting-time suggestion via Graph
`POST /me/findMeetingTimes`. Today the tool only does `getSchedule` + a naive local
interval-overlap finder that ignores per-attendee working hours.

## Steps

- [ ] Add a `find-time --server` path (or a `suggest` subcommand) wrapping
      `/me/findMeetingTimes` with server-side ranking.
- [ ] Expose its params: `--max-candidates` (maxCandidates), `--min-attendee-pct`
      (minimumAttendeePercentage), meeting duration as ISO8601, attendee `type`
      (required/optional), `--location`, `isOrganizerOptional`.
- [ ] Honor each attendee's real `workingHours` from the getSchedule response
      (currently parsed in docstring shape but dropped in `schedule.py`).

## Notes

- Independent of findMeetingTimes, harden the existing `getSchedule` path (file these as
  todos if splitting): validate `--interval` to 5–1440 (availability path doesn't),
  guard >20 attendees (getSchedule cap → opaque 400), add `--tz` override, add result
  `--limit`/`--max` to the local slot finder.
- Slot overlap math uses naive local datetimes — DST-unsafe (AGENTS.md flags tz as
  high-risk). Server-side findMeetingTimes sidesteps this; the local finder still has it.

