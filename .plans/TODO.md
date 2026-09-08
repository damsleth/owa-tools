# TODO

Reconciled against local checkout `3d4336f` on 2026-09-08.
Prior completed items are in [DONE.md](DONE.md); historical plans are in [done/](done/).
Review priorities use P1 for high-impact defects and P2 for other correctness/contract work.

## Code review remediation

See [review findings and acceptance criteria](reviews/2026-09-08/REVIEW.md).
Offline reproductions are retained beside the report. Implementation is pending.

- [ ] P1 R1: make Drive no-force uploads fail closed and enforce server-side no-overwrite
- [ ] P1 R11: validate SWODP split replacements before deleting existing Pending cards; retain partial-progress evidence
- [ ] P1 R4/R5/R9: close escaped-body, fan-out error, and signed-URL logging leaks
- [ ] P1 R2/R3: make scheduling output JSON-safe and refuse free-time claims for failed attendees
- [ ] P2 R6/R7: fix fan-out exit-status consistency and canonical binary-command guards
- [ ] P2 R8: map transport timeouts and interrupted reads to typed network errors
- [ ] P2 R10: propagate Teams page-cap truncation to CLI results
- [ ] P2 R12: stop org-chart manager traversal cleanly on top-of-chain 404
- [ ] P2 review follow-ups: verify scheduling timezones and frozen Graph data assets; reconcile semantic docs drift (see reviews/2026-09-08/REVIEW.md)

## Active plans

- [owa-places](owa-places.md): partially implemented; request/response contract remains unverified. Capture a sanitized valid payload before treating the shipped CLI as operational.
- [owa-pim](owa-pim.md): deferred; no package exists here. Broker dependency and tenant feasibility require separate verification/authorization.
- [SWODP production readiness](owa-swodp-production-readiness.md): Recall implementation complete; live acceptance remains outstanding.

## Event-driven verification

- [ ] owa-swodp: live-verify Submit then Recall on the next legitimate Pending production card
- [ ] owa-swodp: capture natural expired-session signal and verify setup recovery

Historical TUI work is retired from this CLI-only repository; see [snapshot](done/legacy-todo-2026-09-08.md).
