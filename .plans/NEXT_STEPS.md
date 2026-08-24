# owa-swodp next steps

> **Status (2026-08-24): live production verification COMPLETE. All of Phase 2
> passed and the baseline was restored. Phase 3's `task` lookup is verified and
> produced one fix. Phases 4 and 5 are done. Only the Phase 6 release remains,
> pending explicit operator instruction.**

## Live production results (2026-08-24)

Test week `2026-08-24` (empty before and after). Writes were executed by the
operator because the auto-mode permission classifier blocks production mutation
from the agent; every verification read was run by the agent with the bare binary.

| Step | Result | Evidence |
| --- | --- | --- |
| 2.3 locked-card no-op | PASS | `skipped, state=Approved`, exit 15, week `2026-08-17` byte-identical afterwards (4 rows, Admin still 2h/Approved/same comments) |
| 2.1 create | PASS | one `created`, `sys_id fa6f509b…bf0f`, exit 0, no verification warning; card `Pending`/`Admin`/Sun 0.25/total 0.25, description persisted exactly as sent |
| 2.2 update | PASS | one `updated`, same `sys_id`, Sun 0.25 → 0.5, new description, still exactly one Admin card |
| 2.4 delete | PASS | one `deleted`, exit 0, week `2026-08-24` empty, `2026-08-17` matches the pre-test snapshot |

This proves against the live API: POST-without-comments → PATCH-comments → GET
verification, Pending-only PATCH, identity matching without duplication, delete,
and locked-card refusal with the documented exit code.

Phase 3 findings:

- `task <known-number>` returns the normalized `{sys_id, number}` with exit 0.
- **Fixed:** `task <unknown-number>` printed `null` and exited 0. It now raises
  `NotFoundError` (exit 13), matching every other tool in the suite. Regression
  test added in `src/tests/swodp/test_cli.py`.
- Session expiry remains **unverified and accepted as a documented residual
  risk**. It cannot be forced without damaging the Edge profile, which the plan
  forbids. The offline auth-status and HTML-redirect paths are covered; the real
  server signal is unknown and `docs/swodp.md` now says so explicitly.

## 2026-08-24 corrections (read these before running anything)

- **Never use `rtk proxy` for verification reads.** It silently dropped 3 of 5
  rows and rewrote `state` from `Approved` to `Submitted` on
  `owa-swodp cards --week-start 2026-08-17 --range-weeks 1`. The original Phase 1
  gate below was validated against that corrupted output and was wrong. Every
  command in this plan must be run as the bare binary, not through `rtk proxy`.
- **Week `2026-08-17` is not a usable test week.** It actually holds four cards:
  Admin 2h Approved, Project 21h Submitted, Vacation 15h Approved, Project 3h
  Processed. The `admin` identity is taken by an Approved card.
- **Test week is now `2026-08-24`**, which is empty. Category `admin`, Sunday
  0.25h.
- **Phase 2.3 (locked-card protection) is PASSED.** The 2.1 attempt against week
  `2026-08-17` hit the Approved Admin card and returned
  `{"action": "skipped", "detail": "state=Approved"}` with `ok: false`. The card
  was re-read afterwards and is unchanged (2h, Approved, same comments). A PATCH
  against a non-Pending card is refused, proven against the live API.
- Remaining live work: 2.1 create, 2.2 update, 2.4 delete on week `2026-08-24`,
  plus Phase 3's read-only `task` lookup.

## Follow-ups discovered 2026-08-24 (not implemented)

- **Description is mandatory.** A time card saved with a blank Description is
  rejected by the timesheet portal with
  `The mandatory field "Description" is not filled in.` and blocks submission of
  the entire timesheet. Write rows now require a non-empty `description` unless
  they are `remove` rows, refused before any request is sent. Note the rule is
  enforced at the portal/save layer, not on insert: a `project_work` card was
  observed alive in state `Pending` with `comments: ""`, so the existing
  POST-without-comments then PATCH-comments sequence stays valid.
- **State transitions are a different endpoint.** `Pending -> Submitted` (and
  Approve/Reject/Recall) go through
  `timecardprocessor.do?sysparm_processor=TimeCardPortalService&sysparm_name=updateTimeCardState`,
  form-encoded as `new_state=<State>&timecard_id=<sys_id>`, not the Table API.
  `owa-swodp` has no submit command and adding one is a separate decision:
  submitting a timesheet is irreversible without a recall, so it would need its
  own confirmation story.

## Decision record

- There is no usable dedicated SWODP UAT environment for this account.
- The operator explicitly accepted a production-only verification on 2026-08-22.
- The effective blast radius is the operator's own time-card data; the account is
  not a SWODP administrator.
- Production testing does not relax the implementation safeguards: operate on one
  reviewed row at a time, mutate only `Pending` cards, snapshot before every
  write, verify immediately after it, and restore the starting state before moving
  on.
- Do not use a submitted or approved card as the reversible test record. The only
  allowed interaction with one is a deliberate no-op protection check.

This production-only decision supersedes the original UAT-first test assumption
for this verification run. Keep `--instance uat` and its isolated sidecar support
in the CLI for any future environment that becomes available.

## Verified so far

- [x] `owa-swodp` implementation and offline tests exist under `src/owa_swodp/`
  and `src/tests/swodp/`.
- [x] Focused verification passed: 60 tests, Ruff, and compileall.
- [x] The editable install was refreshed and
  `~/.local/bin/owa-swodp -> <repo>/.venv/bin/owa-swodp` resolves correctly.
- [x] `owa list` reports `owa-swodp 1.4.0` from the checkout.
- [x] Production `status --json` authenticated as `CarlJoakim.Damsleth` and
  completed a Table API probe.
- [x] Production sync for week `2026-08-17` completed: 12 history rows, 4 week
  cards, 3 Other-category mappings, and the expected non-fatal
  `resource_allocation` 403 warning.
- [x] Baseline for week `2026-08-17`: one Submitted Vacation card with 15 hours
  on Monday and Tuesday; no Pending card was present.
- [ ] No live POST, PATCH, or DELETE has been executed yet.

## Phase 1: freeze the production baseline

Run immediately before the first mutation and retain the redacted JSON output in
the session evidence. Do not persist cookies, `g_ck`, debug headers, or raw HTTP
payloads.

```bash
owa-swodp status --json
owa-swodp cards --instance prod --week-start 2026-08-24 --range-weeks 0
owa-swodp categories --instance prod
```

Gate:

- Authentication is the expected user.
- The week still contains the known Submitted Vacation card.
- There is no existing `Pending` `admin` card for that week.
- The category map still resolves `Admin` to raw value `admin`.
- Stop if any assumption differs; choose a new isolated identity/week before
  writing.

## Phase 2: reversible production write cycle

Use four separate one-row plans. Show each JSON payload and current card state to
the operator before running its `--confirm` command. Store temporary plans under
`/private/tmp`, never in the repository.

### 2.1 Create and verify

Proposed test record for the week beginning `2026-08-17`:

```json
[
  {
    "category": "admin",
    "days": [0, 0, 0, 0, 0, 0, 0.25],
    "description": "owa-swodp production verification 2026-08-23"
  }
]
```

Run the production write only after the final payload is reviewed:

```bash
owa-swodp write --instance prod --week-start 2026-08-24 \
  --file $S/create.json --confirm
owa-swodp cards --instance prod --week-start 2026-08-24 --range-weeks 0
```

Acceptance:

- The result is exactly one `created` action with a `sys_id`.
- The new card is `Pending`, category `Admin`, and has exactly 0.25 hours on
  Sunday.
- The description is present exactly as sent. No verification warning is
  returned; this proves POST without comments, PATCH comments, and GET
  verification against the real API.
- The Submitted Vacation card is unchanged.

If POST succeeds but description verification fails, do not retry the batch.
Inspect the created `sys_id`, repair or remove that exact Pending card, capture the
evidence, then fix the implementation offline.

### 2.2 Update and verify

Update the same identity to prove Pending-only PATCH behavior:

```json
[
  {
    "category": "admin",
    "days": [0, 0, 0, 0, 0, 0, 0.5],
    "description": "owa-swodp production verification update 2026-08-23"
  }
]
```

Acceptance:

- The result is one `updated` action for the same `sys_id`.
- Sunday changes from 0.25 to 0.5 and the updated description is visible.
- No duplicate Admin card is created.

### 2.3 Prove locked-card protection

Submit a one-row plan targeting category `vacation` for the same week. The
existing record is Submitted, so the expected result is `skipped,
state=Submitted` and process exit 15. Read the week again and prove that its hours
and description did not change.

This is a no-op safety test. Treat any mutation of the Submitted card as a stop
condition and a release blocker.

### 2.4 Delete only the test card and restore baseline

```json
[
  {
    "category": "admin",
    "days": [0, 0, 0, 0, 0, 0, 0],
    "remove": true
  }
]
```

Acceptance:

- The result is exactly one `deleted` action.
- A final cards read contains no Admin card for the test week.
- The Submitted Vacation card matches the Phase 1 snapshot.
- Re-running the removal is not part of the test: the batch is not retry-safe and
  a missing card would correctly produce a skipped/conflict result.

## Phase 3: remaining live behavior

- [ ] Exercise `task <known-task-number>` against production and verify its
  normalized result without writing a project card.
- [ ] Run a realistic same-session request sequence through the write command and
  record that `g_ck` remains valid through preflight GET, POST, PATCH, and
  verification GET. Phase 2.1 satisfies this if it passes cleanly.
- [ ] Confirm the natural expired-session response when it eventually occurs.
  Do not damage or delete the working Edge profile to force expiry. Record whether
  SWODP returns 401/403 or HTML/redirect content, confirm exit 11 plus the setup
  remediation, then prove `reseed` or `setup` restores access.
- [ ] Decide explicitly whether empirical expiry behavior is a release blocker or
  a documented residual risk. The offline HTML-login and auth-error paths are
  already covered, but the real server signal is not yet known.
- [ ] Confirm credentials and debug payloads remain redacted throughout the live
  transcript. Delete any local evidence file containing raw cookies, `g_ck`, or
  signed URLs.

## Phase 4: reconcile implementation and documentation

After the live cycle, make any necessary fixes and add a regression test for every
observed discrepancy. Then update:

- `docs/swodp.md`, `src/owa_swodp/AGENTS.md`, root `AGENTS.md`, and the private
  `cj-owa-tools` skill so they no longer claim that UAT is currently available or
  universally required. Document the production-only exception as explicit
  operator authorization plus snapshot/write/verify/restore controls.
- `.plans/done/swodp-cli.md` and `.plans/DONE.md` with the actual production
  results, including whether create/update/locked-skip/delete and description
  verification passed.
- `CHANGELOG.md` with user-visible behavior and any live-test fixes.
- `docs/swodp.md` with the confirmed expired-session signal when known; otherwise
  label it as unverified rather than implying a specific server response.

Do not weaken Pending-only mutation, confirmation, row validation, the 200-row
limit, redaction, or prod/UAT profile isolation.

## Phase 5: final verification gates

Run narrow checks first:

```bash
.venv/bin/ruff check src/owa_swodp src/tests/swodp
.venv/bin/python -m pytest -q src/tests/swodp
.venv/bin/python -m compileall -q src/owa_swodp
```

Then run the repository gates:

```bash
.venv/bin/ruff check .
.venv/bin/python -m compileall -q src
.venv/bin/python src/scripts/check_stdlib_only.py
.venv/bin/python src/scripts/check_no_secrets.py
.venv/bin/python src/scripts/check_docs_sync.py
.venv/bin/coverage run --source=owa_core -m pytest -q
.venv/bin/coverage report --fail-under=95
.venv/bin/python -m pytest -q --cov --cov-fail-under=90
```

Build and verify packaging with the sandbox-safe cache:

```bash
env UV_CACHE_DIR=/private/tmp/owa-tools-uv-cache uv build
.venv/bin/python src/scripts/check_artifacts.py dist/*
.venv/bin/python src/scripts/check_console_smoke.py
```

Also verify:

- `owa list`, `owa schema --tool owa-swodp`, `owa-swodp --doctor --json`, and
  `owa-swodp --version` agree on the installed surface.
- A clean wheel/sdist install exposes `owa-swodp`; do not rely only on the local
  symlink or editable install.
- The worktree contains no build artifacts, virtualenv changes, temporary write
  plans, session material, or secrets.

## Phase 6: commit and release

Keep the history scoped:

1. Commit the `owa-swodp` feature, tests, docs, registry, and contract integration
   together after production verification passes.
2. If live verification finds defects, commit their fixes with the feature or as a
   clearly named follow-up before the release commit.
3. Verify the latest public tag and choose the next minor version because this is
   a new user-visible binary. With `v1.4.0` as the current tag, the expected target
   is `v1.5.0`.
4. Create a separate `release: v1.5.0` commit updating `pyproject.toml` and
   `CHANGELOG.md`.
5. Cut the release only on explicit operator instruction: push `main`, create and
   push an annotated tag, build and verify artifacts, publish to PyPI, wait for the
   GitHub release workflow, update the Homebrew tap, and run
   `brew upgrade owa-tools`.
6. Verify the installed Homebrew/PyPI binary independently of the checkout, then
   remove the development-only symlink if it masks the packaged binary.

Never retag a public version or publish a second artifact under an existing
version.

## Completion criteria

`owa-swodp` is finished only when all of these are true:

- The controlled create, update, locked-card no-op, and delete cycle passes in
  production and restores the baseline.
- Description persistence is proved against the live API.
- The full offline suite, coverage gates, artifact checks, and clean-install smoke
  pass after the live findings are incorporated.
- Documentation accurately describes the production-only verification decision
  and any remaining session-expiry uncertainty.
- The implementation is committed with no secrets or local artifacts.
- The requested release is published and independently installable, or the work is
  explicitly handed off as verified-but-unreleased.
