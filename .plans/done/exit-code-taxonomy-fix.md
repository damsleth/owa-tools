# exit-code-taxonomy-fix

> **DONE 2026-06-29** — see [../DONE.md](../DONE.md). Every networked `api.py`
> raises its recoverable `OwaError`; the central handler maps it to the
> documented exit code. End-to-end contract test added on owa-cal.

_Created 2026-06-23_

**Priority: P0** — systemic contract violation, agent-facing, mechanical fix.

## Goal

Make the documented exit-code taxonomy (`AGENTS.md:46-56`: 10 network, 13 not-found,
14 rate-limited, 15 conflict, 20 internal) actually reach the shell. Today every
networked tool collapses all five to exit `1`.

## Root cause

Each `src/owa_*/api.py` re-raises `AuthExpiredError`/`ScopeInsufficientError` (so 11/12
propagate correctly) but for the other five recoverable `OwaError`s it calls
`emit_error(error)` — which *computes and returns* the right code — then `return None`,
discarding it. Every CLI handler maps `if payload is None: return 1`. Verified pattern at
`owa_cal/api.py:35-42`; identical in cal, mail, graph, drive, people, sched, todo,
planner, sites, teams, ado. (owa-vids and owa-doctor differ; owa umbrella is separate.)

## Steps

- [ ] Pick the fix shape once, then replicate: in each `api.py`, change the
      `except (Conflict|Internal|Network|NotFound|RateLimited)` branch to `raise error`
      (like the auth branch) instead of `emit_error` + `return None`; let top-level
      `run_with_output_modes` / `_main` `except OwaError: emit_error` produce the code.
- [ ] Delete the now-dead `if <payload> is None: return 1` callsites (counts: mail 20,
      ado 12, todo 8, people 7, drive 6, teams/sites/planner/graph/cal 5, sched 3).
      Where `None` was a legitimate "empty but ok" signal, keep it — audit each callsite.
- [ ] Fix the paginate helpers too (`paginate_all`/`ado_paginate`/`paginate_sp`/
      `api.paginate`) — same swallow-and-return-None on mid-stream errors.
- [ ] owa-planner: ensure 412 Precondition (ConflictError → 15) propagates — needed for
      the write phase (see [[owa-planner-write-support]]).

## Notes

- ~70 callsites, ONE pattern. Per-tool commits (one domain per commit per AGENTS.md) or
  one sweep if tests stay green.
- Auth/scope (11/12) already correct — don't touch those branches.
- Verify: contract tests asserting mocked 404→13, 429→14, 5xx→20, network→10, 409/412→15
  for at least cal+mail+graph+ado; `--err-json` code must keep matching process exit;
  run `src/tests/contract/` + 90% coverage gate.

