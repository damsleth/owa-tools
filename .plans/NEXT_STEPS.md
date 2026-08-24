# owa-swodp next steps

> **Status (2026-08-23): implementation complete; live read path verified;
> controlled production mutation verification, final review, commit, and release
> remain.**

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
rtk proxy owa-swodp status --json
rtk proxy owa-swodp cards --instance prod --week-start 2026-08-17 --range-weeks 1
rtk proxy owa-swodp categories --instance prod
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
rtk proxy owa-swodp write --instance prod --week-start 2026-08-17 \
  --file /private/tmp/owa-swodp-create.json --confirm
rtk proxy owa-swodp cards --instance prod --week-start 2026-08-17 --range-weeks 1
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
rtk proxy .venv/bin/ruff check src/owa_swodp src/tests/swodp
rtk proxy .venv/bin/python -m pytest -q src/tests/swodp
rtk proxy .venv/bin/python -m compileall -q src/owa_swodp
```

Then run the repository gates:

```bash
rtk proxy .venv/bin/ruff check .
rtk proxy .venv/bin/python -m compileall -q src
rtk proxy .venv/bin/python src/scripts/check_stdlib_only.py
rtk proxy .venv/bin/python src/scripts/check_no_secrets.py
rtk proxy .venv/bin/python src/scripts/check_docs_sync.py
rtk proxy .venv/bin/coverage run --source=owa_core -m pytest -q
rtk proxy .venv/bin/coverage report --fail-under=95
rtk proxy .venv/bin/python -m pytest -q --cov --cov-fail-under=90
```

Build and verify packaging with the sandbox-safe cache:

```bash
rtk proxy env UV_CACHE_DIR=/private/tmp/owa-tools-uv-cache uv build
rtk proxy .venv/bin/python src/scripts/check_artifacts.py dist/*
rtk proxy .venv/bin/python src/scripts/check_console_smoke.py
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
   `rtk proxy brew upgrade owa-tools`.
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
