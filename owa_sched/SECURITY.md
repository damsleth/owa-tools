# Security model for owa-sched

## TL;DR

`owa-sched` is a personal productivity tool that reads free/busy
information for a specified set of attendees. It holds no secrets
- only an optional profile alias - and `owa-piggy` owns the
refresh token. Don't deploy it for other people.

## What this actually is

`owa-sched` is a thin client over Microsoft Graph
`/me/calendar/getSchedule`. It exchanges a short-lived access token
(via `owa-piggy`) for free/busy data on a list of attendees. The
endpoint itself enforces visibility - calendars hidden from the
caller surface as a per-entry error rather than data leakage.

## Threat model

**In scope:** single-user, single-machine use. The caller runs
`owa-sched` under their own account against their own tenant.

- `~/.config/owa-sched/config` contains only profile alias and
  default work-day strings. No credentials.
- Access tokens are held in memory for one call.
- Attendee emails are passed through to Graph verbatim. Don't
  sanitise them client-side; Graph is the source of truth on what
  the caller is allowed to see.

**Out of scope:** multi-user shared installs, deploying as a
service, querying calendars outside the caller's permissions.

## What `owa-sched` will never do

- Write a token to disk.
- Modify any attendee's calendar (this tool is read-only).
- Bypass Graph's visibility rules.

## Reporting issues

Open a private security advisory on GitHub.
