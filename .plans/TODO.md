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

- [ ] owa-ado: add `pr-create`. Opening a PR is the one release step the CLI cannot do, so it falls back to the portal or to raw REST. Hit on 2026-09-14 opening NOCOS-Main `test` -> `main` (PR 3869), which had to go through `POST _apis/git/repositories/{repo}/pullrequests` with an owa-piggy `devops` token; `az devops` is no help, it wants its own `az devops login` even with `az account` signed in. Mirror `wi-create`: `--source`/`--target` refs, `--title`, `--description` (accept `-` for stdin, descriptions are long), `--repo`, `--draft`, `--confirm`. Read back `mergeStatus` and `hasConflicts` after create, the way the swodp commands verify their own writes.

## Event-driven verification

- [ ] owa-swodp: live-verify Submit then Recall on the next legitimate Pending production card
- [ ] owa-swodp: capture natural expired-session signal and verify setup recovery

Historical TUI work is retired from this CLI-only repository; see [snapshot](done/legacy-todo-2026-09-08.md).
