# owa-shifts

_Created 2026-06-01_

## Goal

Add an `owa-shifts` consumer binary for the Teams Shifts app: read a team's
schedule — my shifts, the team's shifts in a date window, open shifts, time-off,
and time-off reasons / scheduling groups. Read-only v1. Niche; build only if a
target tenant actually uses Shifts.

## Feasibility — VERDICT: BLOCKED by client preauth (probed 2026-06-01, dno)

Shifts IS now provisioned for Casa Damsleth (team `9e65ab76-…`), reachable in the
browser via the Frontline/StaffHub backend. But owa-piggy can't reach it:

1. **Graph door is closed**: `GET /teams/9e65ab76-…/schedule` → 200 but still
   `enabled:false, provisionStatus:NotStarted`; `/schedule/shifts` → **404**. Shifts
   was provisioned through the StaffHub/flw path, which does NOT surface on the Graph
   `/teams/{id}/schedule` object. So the clean Graph API has no data.

2. **StaffHub door is preauth-walled**: the data lives behind
   `aud https://api.manage.staffhub.office.com` (scp `Shift.ReadWrite.All`), but that
   resource (client `aa580612`) has NOT preauthorized owa-piggy's One Outlook Web
   client (`9199bf20`). Minting it fails hard:
   `AADSTS65002: Consent between first party application '9199bf20…' and first party
   resource 'aa580612…' must be configured via preauthorization`. And `aa580612` is
   NOT in the FOCI client CSV ([[foci-reference-sources]]), so redeeming the FRT as
   that client wouldn't work even if owa-piggy gained a client-id override.

**Not buildable on the current owa-piggy.** See [[owa-piggy-token-scope-limits]].

- [ ] DO NOT build. Unblock paths, both speculative:
      (a) owa-piggy adds a FOCI client-id override AND a FOCI client (e.g. Teams
          `1fec8e78`) turns out to be preauthorized for the StaffHub resource; or
      (b) Microsoft surfaces this team's Shifts data through Graph `/schedule`
          (currently NotStarted there). Re-probe the Graph endpoint if that changes.

### Last-ditch flw probe (HAR at .plans/shifts.har, 2026-06-01) — confirms blocked

The real backend is `https://flw.teams.cloud.microsoft/svc-eur1/...`, and the HAR's
auth headers were redacted on export, so I tested every audience owa-piggy CAN mint
against `flw …/api/account/settings`:
- `teams` (api.spaces.skype.com) → **403** (identity accepted, no Shift authorization
  — dead end; no route from 403→200 without scopes only the native client holds)
- `csa`/`ic3`/`presence`/`outlook`/`graph` → **401** (wrong audience)
- `uis`/StaffHub `--scope` → won't even mint (AADSTS65002)

The one audience flw actually wants (`api.manage.staffhub.office.com`,
scp `Shift.ReadWrite.All`) is the walled one. Definitively not reachable.

### flw Shifts API surface (mapped from HAR — for if-ever-unblocked)

Base `https://flw.teams.cloud.microsoft/svc-eur1/api`, custom headers `apiversion`,
`clientplatform`, `shiftrclientversion`, `x-ms-shft-dev`, `x-ms-shft-fp`:
- `GET /tenants/{tid}/teams/TEAM_{teamId}/shifts/unique` — shifts
- `GET /tenants/{tid}/teams/TEAM_{teamId}/members`
- `POST /teams/TEAM_{teamId}/bulk/getDataInDateRange` — windowed data
- `GET /teams/TEAM_{teamId}/conflictdismissals`, `GET /sync/all`, `GET|PUT /account/settings`
- `GET /users/{oid}/teamsPolicySettings`
- `POST /v2/teams/TEAM_{teamId}/timeclock/clockin` — **clock in**
- `POST /v2/teams/TEAM_{teamId}/timeclock/TCK_{id}/...` — clock out / break on an entry
Note `TEAM_` prefix on team ids and `TCK_` prefix on timeclock entry ids.

## Steps

- [ ] Scaffold `src/owa_shifts/` per docs/new-tool-onboarding.md.
- [ ] Define `CommandSpec`s (audience `graph`, all read/non-mutating):
      - `schedule --team <id>` — `GET /teams/{id}/schedule` (provisioning status)
      - `shifts --team <id> [--from --to]` — `GET /teams/{id}/schedule/shifts`
      - `open-shifts --team <id>` — `GET /teams/{id}/schedule/openShifts`
      - `time-off --team <id>` — `GET /teams/{id}/schedule/timesOff`
      - `time-off-reasons --team <id>` — `.../timeOffReasons`
      - `groups --team <id>` — `.../schedulingGroups`
- [ ] Team discovery: reuse the `/me/joinedTeams` call (shared with owa-teams if it
      lands first; otherwise a local helper).
- [ ] HTTP + pagination via `owa_core.http.request`.
- [ ] Normalizers: shift (user→name, start/end, theme, notes from
      sharedShift/draftShift), timeOff, openShift.
- [ ] `--pretty` schedule view: shifts grouped by day, then by person.
- [ ] Tests: full onboarding minimum set incl. from/to window param builder;
      scanner + stdlib checker include pkg.
- [ ] Register everywhere: pyproject (packages + `owa-shifts` script + coverage),
      registry.CONSUMER_TOOLS, README table, docs/shifts.md, CHANGELOG, root
      AGENTS.md index, owa_shifts/AGENTS.md, check_docs_sync.py DOCS map.
- [ ] Acceptance per onboarding doc.

## Notes

- Shift records carry both `sharedShift` (published) and `draftShift` (unpublished)
  — surface the shared one by default; expose draft only with a flag.
- Times are UTC; render in the profile/default tz (reuse owa-cal's tz handling
  rather than re-implementing).
- Clock-in/out and swap-request writes are mutating + workflow-heavy — explicitly
  out of scope for v1, maybe never. Read schedule is the 90% use case.
- Lowest priority of the five proposed tools — depends entirely on tenant Shifts
  adoption.
