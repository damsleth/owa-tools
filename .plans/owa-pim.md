# owa-pim

_Created 2026-07-01_

## Feasibility — VERDICT: BLOCKED, pending an owa-piggy-side auth change (sibling repo)

PIMELIM's core operation (self-activate a PIM-eligible directory role via Graph)
needs a delegated token carrying `RoleManagement.ReadWrite.Directory`. Probed
directly against owa-piggy's current pinned client:

```
$ owa-piggy token --profile acme --scope "https://graph.microsoft.com/RoleManagement.ReadWrite.Directory" --json
ERROR: invalid_request: AADSTS65002: Consent between first party application
'9199bf20-a13f-4107-85dc-02114787ef48' and first party resource
'00000003-0000-0000-c000-000000000000' must be configured via preauthorization -
applications owned and operated by Microsoft must get approval from the API
owner before requesting tokens for that API.
```

`9199bf20-...` (One Outlook Web) is not preauthorized for this scope, and never
will be — it's not in that app's fixed consent set (same wall as owa-shifts/
StaffHub). `owa_core.auth`'s `--scope` passthrough works mechanically end-to-end
(confirmed via `owa-piggy`/`owa_core.auth.get_token` source read) but scope
resolution can't grant a permission the underlying client was never consented
for.

**Decided auth path** (matches owa_ado's existing precedent — `devops` audience,
"non-FOCI capture path", see `src/owa_ado/auth.py`): add a new owa-piggy audience
(`pim`) backed by Azure CLI's client ID (`04b07795-8ddb-461a-bbee-02f9e1bf7b46`),
captured via its own one-time setup/consent step per profile — not a silent FOCI
refresh-token pivot. Same shape as how `devops` already works: one browser
consent the first time, headless refresh forever after via the normal
`owa-piggy token` broker path. No new app registration (Azure CLI is an existing
first-party MS app); no local token cache inside owa-pim (owa-piggy still owns
all token material).

This is a **cross-repo blocking dependency** — the change lives in
`~/code/owa-piggy/`, not here. owa-pim's scaffolding, models, scheduling
algorithm, and tests can be built and mocked now, but the auth-required
commands (`activate`/`ensure-coverage`/`status`) cannot be exercised live, and
the tool cannot ship/release, until:

## OPEN — must be resolved before owa-pim can ship

- [ ] owa-piggy: add a `pim` audience (`scopes.py` `KNOWN_AUDIENCES`) targeting
      Azure CLI's client ID, with its own capture/setup path (mirror `devops`).
- [ ] Live probe with the new audience: `owa-piggy token --audience pim --json`
      after a fresh one-time setup — confirm it actually returns
      `RoleManagement.ReadWrite.Directory` in the granted `scope` field for a
      real tenant (Azure CLI being preauthorized tenant-wide is typical but not
      guaranteed — this is the one unverified assumption in the whole plan).
- [ ] Confirm the resulting token also carries enough for the read-side calls
      (`roleManagement/directory/roleDefinitions`,
      `roleAssignmentScheduleInstances`) — these are lower-privilege reads,
      should ride the same token, but verify rather than assume.
- [ ] Decide whether `pim` audience setup requires the caller to already hold a
      PIM-eligible role assignment (yes — owa-pim, like PIMELIM, assumes
      eligibility already exists and does not manage eligibility itself).

## Command surface (stateless CLI, no daemon — per architecture.md)

owa-pim ships one-shot idempotent commands; unattended repetition is the
*user's* cron/systemd/launchd job calling `owa-pim ensure-coverage`
periodically — owa-pim does not bundle a scheduler or a token cache (that's
owa-piggy's job, suite-wide). Optionally document example unit files in
`docs/pim.md` as copy-paste convenience, no code ships for them.

| Command | Summary |
| --- | --- |
| `ensure-coverage` | Core loop: for each configured role, compute the coverage gap against existing active/pending schedule instances, submit `selfActivate` requests to fill it, cancel/retry zombie pending requests. Idempotent — safe to run every N minutes from cron. |
| `status` | Report ACTIVE / SCHEDULED / INACTIVE + remaining time per configured role. |
| `activate` | One-off manual activation of a single role (bypasses the gap-fill horizon; for ad-hoc use). |
| `refresh` | Force a token refresh and verify auth (standard suite command). |
| `config` | View or update configuration (standard suite command). |

All mutating commands (`ensure-coverage`, `activate`) are `destructive: true` in
schema (they create real PIM activation requests) and support `--dry-run` to
compute-and-print the planned window without submitting; non-TTY runs (the cron
case) require `--confirm`/`--yes` per the destructive-command contract in
security.md.

## Config contract (owa_core.config.Config allowlist, not .env blocks)

PIMELIM's `ROLE_<N>_NAME`/`ROLE_<N>_REASON` env blocks don't map onto the
allowlist model directly — port as a single `roles` list value instead:

```json
{
  "roles": [
    {"name": "Global Administrator", "reason": "Break-glass coverage"},
    {"name": "Privileged Role Administrator", "reason": "PIM admin work"}
  ],
  "cover_for_hours": 36,
  "activation_duration_hours": 8,
  "activation_time_buffer_minutes": 60,
  "minimum_window_minutes": 5
}
```

- `reason` defaults to `name` if omitted (PIMELIM's existing fallback rule,
  keep it).
- All five keys go in `owa_pim`'s config allowlist; CLI flags (`--roles`,
  `--cover-for-hours`, etc.) override config per-invocation, same precedence
  rule PIMELIM used for CLI-over-.env.
- No `TENANT_ID`/`CLIENT_ID` keys — that's owa-piggy's `pim` audience/profile,
  not owa-pim's config.

## Scheduling / gap-fill algorithm port plan

Port from `pimelim.ps1`'s `Get-PlannedActivationWindows` and helpers into
`owa_pim/api.py` (pure functions, no I/O, unit-testable without mocking Graph):

- `Get-RoleDefinitionByName` → resolve role display name to `roleDefinitionId`
  (one Graph read, cache within a single invocation only — no persistence).
- Anchor logic, unchanged: active role → anchor at active instance's end time;
  inactive + `now=true` → anchor at now; inactive + `now=false` → anchor at
  `now + activation_duration_hours`.
- Gap-fill horizon: walk forward from the anchor, skip windows already covered
  by active/pending instances, emit new activation windows only for the
  uncovered remainder up to `cover_for_hours`.
- Minute-safety helpers ported verbatim in spirit:
  `truncate_to_utc_minute`, `minute_safe_start_after`,
  `minute_safe_end_before`, respecting `activation_time_buffer_minutes` and
  `minimum_window_minutes` (clamped to >= 5, same as PIMELIM).
- Zombie handling: pending requests stuck past a threshold get cancelled and
  retried once; surface a clear status line either way, don't retry silently
  forever.
- Retry-with-backoff on 429/5xx: use `owa_core.http`'s existing retry behavior
  rather than reimplementing PIMELIM's own backoff loop.

## Registration touchpoints checklist

- [ ] `pyproject.toml`: `[project.scripts] owa-pim = "owa_pim.cli:main"`,
      add `owa_pim` to `[tool.setuptools].packages`, add `src/owa_pim` to
      `[tool.coverage.run].source`.
- [ ] `src/owa/cli.py`: register `owa-pim` in the umbrella consumer registry.
- [ ] Root `README.md`: add to top tool list + tool table row.
- [ ] Root `AGENTS.md`: add to tool list + local-AGENTS.md pointer table row
      (`| src/owa_pim/AGENTS.md | changing PIM activation behavior |`).
- [ ] `src/scripts/check_docs_sync.py`: add
      `'owa-pim': ('docs/pim.md', PIM_SCHEMA)` to the `DOCS` dict.
- [ ] `CHANGELOG.md`: new-tool entry.
- [ ] New `src/owa_pim/AGENTS.md` (local, per onboarding template).
- [ ] New `docs/pim.md` (per `docs/AGENTS.md` rules: `example.com`/`.invalid`
      only, no real tenant IDs/role assignments, state owa-piggy owns tokens,
      cross-link `docs/security.md` for the destructive-command/PIM-privilege
      caveat).

## Package skeleton (per new-tool-onboarding.md)

`src/owa_pim/{AGENTS.md, __init__.py, __main__.py, cli.py, api.py, format.py,
models.py}` + `src/tests/pim/{__init__.py, conftest.py, test_cli.py,
test_format.py, test_models.py, test_contract.py}`.

- `models.py`: `RoleConfig`, `ActivationWindow`, `ScheduleInstance` dataclasses.
- `api.py`: thin Graph wrappers (`get_role_definition`, `list_schedule_instances`,
  `list_pending_requests`, `submit_self_activate`, `cancel_request`) over
  `owa_core.http`, re-raising typed `OwaError` subclasses — plus the pure
  gap-fill functions above (no HTTP inside those).
- `format.py`: `--pretty` status table (ACTIVE/SCHEDULED/INACTIVE + remaining
  time), planned-window dry-run output.
- `auth.py`: same thin-wrapper shape as `owa_ado/auth.py`, `AUDIENCE = 'pim'`.

## Tests (per docs/testing.md layers)

- `src/tests/pim/test_models.py`: dataclass validation.
- `src/tests/pim/test_format.py`: pretty/JSON output shapes, fake data only.
- `src/tests/pim/test_cli.py`: flag parsing, dispatch, `--dry-run` vs
  `--confirm`/`--yes` gating on `ensure-coverage`/`activate`, `--doctor`.
- `src/tests/pim/test_contract.py`: schema/help/exit-code contract snapshot.
- Dedicated unit tests for the pure gap-fill/anchor/minute-safety functions in
  `api.py` — this is the highest-value coverage target (port PIMELIM's known
  edge cases: overlapping pending requests, zombie cancellation, DST-adjacent
  boundaries) and doesn't need any mocking.
- `conftest.py`: fake broker/token per suite convention, fake `roleDefinitionId`
  GUIDs, `example.com`-style fake principal IDs — no real tenant data.
- `src/tests/pim/test_live.py`: opt-in only (`OWA_LIVE_TESTS=1` +
  `OWA_PROFILE=<alias>`), gated additionally on the `pim` audience existing —
  cannot be written/enabled until the owa-piggy OPEN items above land.
- No live/contract additions to `src/tests/contract` or `src/tests/compat`
  until the tool actually ships.

## Acceptance checklist (per onboarding doc, condensed)

- [ ] All registration touchpoints above complete.
- [ ] `owa-pim schema` / `--help --json` / `--doctor` implemented and tested.
- [ ] `--agent` / `--err-json` envelopes implemented and tested.
- [ ] Destructive-command confirmation gating tested for non-TTY.
- [ ] Coverage meets suite `fail_under=89` gate; gap-fill/anchor pure functions
      at or near 100% given they need no mocking.
- [ ] `docs/pim.md` written and passes `check_docs_sync.py` / `check_no_secrets.py`.
- [ ] `ensure-coverage`/`status`/`activate` runnable and live-tested against a
      real profile once the `pim` audience exists in owa-piggy — this is the
      final release gate, not a build gate.

## Notes

- PIMELIM's own app-registration/device-code bootstrap is explicitly NOT
  ported — owa-piggy remains the sole owner of refresh tokens suite-wide.
- PIMELIM's local `.token-cache.json` and scheduler unit-file installer are
  explicitly NOT ported — stateless CLI + user-supplied scheduler only,
  matching every other owa-tool.
- Coverage-horizon math is the one genuinely novel piece of domain logic in
  this tool (everything else is a normal Graph CRUD wrapper); treat it as the
  thing worth the most test investment, not the auth plumbing.
