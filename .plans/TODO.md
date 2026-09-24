# TODO

Reconciled against local checkout `3d4336f` on 2026-09-08.
Prior completed items are in [DONE.md](DONE.md); historical plans are in [done/](done/).
Review priorities use P1 for high-impact defects and P2 for other correctness/contract work.

## Code review remediation

See [review findings and acceptance criteria](../.tmp/reviews/2026-09-08/REVIEW.md).
All 12 reproduced defects and locally verifiable follow-ups are fixed.
See [fixes and validation](../.tmp/reviews/2026-09-08/FIXES.md). Historical reproductions
are retained beside the report; completed tasks are archived in DONE.md.


## Active plans

- [owa-places](owa-places.md): partially implemented; request/response contract remains unverified. Capture a sanitized valid payload before treating the shipped CLI as operational.
- [owa-pim](owa-pim.md): deferred; no package exists here. Broker dependency and tenant feasibility require separate verification/authorization.
- [SWODP production readiness](owa-swodp-production-readiness.md): Recall implementation complete; live acceptance remains outstanding.

## Feature gaps


## Event-driven verification

- [ ] owa-swodp: live-verify Submit then Recall on the next legitimate Pending production card
- [ ] owa-swodp: capture natural expired-session signal and verify setup recovery

Historical TUI work is retired from this CLI-only repository; see [snapshot](done/legacy-todo-2026-09-08.md).
- [ ] when fanning out with -A, any token related error, warning or wait time, e.g. due to expired token requiring refresh, should surface immediately, instead of leaving the user waiting for the underlying operation to finish, time out or err. this might require a contract change across all of the owa tools, owa piggy and owa tui
- [ ] owa-sched: audience graph has no Calendars.* scope for owa-piggy tokens → always 403. Switch to audience outlook + https://outlook.office.com/api/v2.0/me/calendar/getschedule (PascalCase body/response); owa-tui sched already does this (owa-tui 04103b7)
- [ ] owa-sched -A returns profiles: [] exit 0 when every profile fails — fan-out silently skips instead of reporting
- [ ] owa_core.http: RateLimitedError should carry retry_after (Retry-After header); expose retry= on owa_mail/owa_cal/owa_people/owa_planner/owa_todo/owa_drive api_get like owa_teams/owa_graph do. Graph 429 ApplicationThrottled/MailboxConcurrency is shared with browser OWA (same One Outlook Web app id)
