# owa-swodp production readiness

_Created 2026-08-25_

## Goal

Close the remaining operational gap in `owa-swodp`: make a submitted card
recoverable through an explicitly confirmed Recall command, without weakening
the existing Pending-only write/delete safeguards or inventing production test
data. Retain live Submit and natural-expiry checks as event-driven evidence.

## Steps

- [x] Discover and document the portal's exact Recall contract from current,
      authenticated read-only assets: eligibility/state rules, processor name,
      `new_state`, reason field, and response shape. Session material stayed in
      memory and out of the transcript.
- [x] Implement `recall <sys-id> --reason <text> --confirm` against the canonical
      processor helper. Preflight must require a recallable state and a non-empty
      reason; GET-verify that the card reaches Recalled.
- [x] Add offline service, CLI, schema, confirmation, error-taxonomy, and
      redaction tests. Keep normal test runs network-free.
- [x] Update help, `docs/swodp.md`, `src/owa_swodp/AGENTS.md`, and `CHANGELOG.md`.
- [x] Run focused checks, then repository contract/security/docs/coverage gates.
- [ ] Hand off live verification to the separate repo todo: use the next real
      operator-owned Pending card, snapshot, Submit, verify Submitted, Recall
      with a reviewed reason, verify Recalled and byte-equivalent card content.
- [ ] Close this plan after the live Submit-then-Recall cycle passes and the
      evidence is recorded. A release requires a separate explicit request.

## Notes

- v1.5.0 is released and independently installed; create/update/delete,
  description persistence, and locked-card refusal were live-verified on
  2026-08-24. The archived evidence is `.plans/done/NEXT_STEPS.md`.
- `submit` success and Recall are covered offline. The checkout can now undo a
  submitted card through the confirmed Recall contract, but that full cycle is
  deliberately waiting for a real operator-owned Pending card.
- Authenticated portal assets confirmed that per-card Recall uses
  `updateTimeCardState` with `timecard_id`, `new_state=Recalled`, and mandatory
  `reason`. The portal exposes `canRecall` per card and permits editing after
  the card reaches Recalled. The CLI uses a conservative Submitted-only
  preflight because the computed `canRecall` flag isn't a Table API field.
- The natural expired-session response remains an accepted residual risk and is
  tracked separately because forcing it would damage a working sidecar.
- Production verification reads must use the bare binary. Never route them
  through an output-filtering proxy.
- Focused tests, contract/compat tests, repository lint/security/docs gates,
  `owa_core` coverage (97%), total coverage (92.80%), artifact inspection, and
  a fresh-wheel console smoke all passed on 2026-08-25.
- The checkout's editable install was refreshed from stale 1.4.0 metadata to
  1.5.0. `owa-swodp --version`, `owa list`, and `owa-swodp schema recall` now
  agree.
- The current production week contained 0 cards on 2026-08-25. Live
  Submit-then-Recall remains event-driven; no throwaway card was created.
