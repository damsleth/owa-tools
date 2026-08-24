# swodp-cli

> **Status: COMPLETE (2026-08-21).** Implemented as `owa-swodp` with
> dedicated prod/UAT Edge sidecars, in-memory CDP session capture, fixed
> ServiceNow reads, and validated Pending-only writes. Live prod status and
> full-sync reads passed; no live writes were attempted because UAT has not
> yet been signed in on this machine.

_Created 2026-08-21_

## Feasibility — VERDICT: VIABLE (spiked and confirmed live against production SWODP, 2026-08-21)

did-cli (the old timesheet tool) is deprecated. SWODP (swodp.service-now.com, a
ServiceNow instance) is the real timesheet system. A colleague's PoC at
`~/code/swodp-enrichment` uses a browser extension to read/write it. The ask: an
agent-friendly CLI, owa-piggy-style auth, no browser extension needed at request time.

The open question going in was whether headless Edge could complete SWODP's SSO
(SAML via the org's AAD/Okta tenant) without a live interactive browser. Spiked via
`owa_piggy.capture`'s `launch_edge`/CDP primitives against a dedicated Edge sidecar
profile:

1. One-time **visible** Edge sign-in into SWODP on a fresh profile → real session
   established (confirmed `window.NOW.user_name` = real username, not `guest`).
2. **Headless** relaunch of that same profile silently round-trips through
   `device.login.microsoftonline.com` and re-authenticates — no prompt, ~3-20s.
3. Cookies (`Network.getCookies`) + `window.g_ck` (CDP `Runtime.evaluate`) extracted
   from that headless session, then used in a **plain `urllib` call with zero
   browser involvement** — confirmed `HTTP 200` with real time_card rows returned.

Full chain validated end-to-end. Nothing here is theoretical — see the build prompt
below for the exact mechanism and the working, already-authenticated sidecar profile
location.

## Build prompt

Paste this as the opening message of a fresh session in this repo (`~/code/owa-tools`).

```
Build swodp-cli: a new owa-tools sibling binary that replaces a browser-extension-based
SWODP (ServiceNow timesheet) integration with headless-Edge session capture, following
owa-piggy's exact capture pattern. This is a from-scratch build in this repo, but the
auth mechanism has ALREADY been spiked and validated end-to-end in a prior session —
read this whole prompt before doing anything, it front-loads what would otherwise take
another full research pass.

## Why this exists

did-cli (the old timesheet tool) is deprecated and dead. SWODP (swodp.service-now.com,
a ServiceNow instance) is the real timesheet system. A colleague built a browser-extension
+ React app PoC at ~/code/swodp-enrichment (still on disk, read-only reference — do NOT
fork or modify it) that matches Outlook calendar events to SWODP time-tracking activities
and writes them back. Kim wants the same capability as an agent-friendly CLI using
owa-piggy-style auth, with NO browser extension required at request time.

## What's already proven (don't re-derive, read the evidence instead)

Read ~/code/owa-piggy/owa_piggy/capture.py and cdp.py first — this is the pattern to
port. capture.py does AAD OAuth token capture (not applicable here — SWODP is cookie/
session-based, not OAuth), but cdp.py (the raw stdlib CDP WebSocket client: find_tab,
CdpSession.call/wait_event) is directly reusable. Copy it verbatim into the new package,
same as its existing twin in owa-piggy/scripts/scrape_edge.py (keep-in-sync marker
convention) — don't reimplement CDP framing from scratch.

The validated flow (confirmed live against production SWODP, not theoretical):
1. A dedicated Edge sidecar profile (NOT shared with owa-piggy — different credential
   domain, different purpose) at ~/.config/owa-swodp/edge-profile/ ALREADY EXISTS and
   is already authenticated as Kim. Don't delete or re-sign-in unless it's broken —
   verify it still works first (see "First step" below).
2. One-time setup (already done, but the CLI must support re-doing this for reinstalls):
   launch Edge VISIBLY (launch_edge(profile_dir, port, headless=False,
   url='https://swodp.service-now.com/tcp')) and let the user sign in by hand
   (Okta/AAD, whatever MFA the tenant wants). No /token interception needed — just
   wait for window.NOW.user_name (via CDP Runtime.evaluate) to become a real
   username instead of 'guest' or null.
3. Silent reseed: launch Edge HEADLESS on the SAME profile dir, same URL. The org's
   SAML SSO round-trips through device.login.microsoftonline.com and completes
   silently within ~3-20s (confirmed timing varies) because the AAD session persists
   in the profile. Poll window.NOW.user_name until it's non-guest, or timeout (use
   ~45s budget, checked empirically to be enough with margin).
4. Extract via CDP: `window.g_ck` (Runtime.evaluate) is the ServiceNow anti-CSRF
   token; cookies via Network.getCookies({urls: ['https://swodp.service-now.com']})
   (JSESSIONID, glide_session_store, glide_sso_id, glide_user_route, etc. — all
   httpOnly, which is fine, CDP's Network.getCookies reads them regardless).
5. Close Edge. Make PLAIN stdlib HTTP calls (urllib, no browser) to
   https://swodp.service-now.com/api/now/table/<table> with headers
   {'X-UserToken': g_ck, 'Cookie': '<name>=<value>; ...', 'Accept': 'application/json'}.
   CONFIRMED WORKING: a GET against time_card returned real timesheet rows this way.

## First step when you start

Verify the existing sidecar profile still authenticates before building anything:
launch headless Edge against ~/.config/owa-swodp/edge-profile/ pointed at
https://swodp.service-now.com/tcp, poll for window.NOW.user_name != 'guest' up to 45s.
If it still works, proceed. If it's expired/broken, that itself tells you what the
session lifetime looks like (useful data) — fall back to a visible re-signin.

## The API surface to port

Read ~/code/swodp-enrichment/outlook-matching/extension/background.js in full (599
lines) — it is the authoritative, already-debugged implementation of every read and
write query this CLI needs to replicate. Also read outlook-matching/README.md's
"Automatisk SWODP-lasting" and "Hente egne data manuelt" sections for the plain-fetch
equivalents and prose explanation of the same queries. Do not redesign the query
shapes — port them as-is; they encode real, hard-won fixes.

Reads needed:
- time_card table: week cards (range query, ±N weeks), full history, category map
  (for Other-type categories like Admin/Vacation)
- resource_allocation table: allocated projects (last ~90 days)
- task table: lookup by task number (for creating new cards)

Writes needed (all via the same X-UserToken + Cookie headers, plain HTTP):
- POST to create a time_card
- PATCH to update day fields + description on an existing card
- DELETE a Pending card

## Gotchas already discovered — do not rediscover these the hard way

- **`comments` (the Description field) is silently dropped on POST.** Verified
  empirically in the PoC: 227 chars sent, field empty after. Fix: POST without it,
  then PATCH the description in a second call, then GET the card back and verify
  the field actually landed (empty description otherwise passes silently and tcp
  submission requires it non-empty).
- **Only cards in state `Pending` may be touched.** Submitted/Approved cards must be
  skipped with a clear "skipped, state=X" result, never mutated.
- **`resource_allocation` 403s for accounts without a resource role; `time_card`
  does not.** This is a per-account ACL difference, not a bug. Reads must degrade
  per-table: a 403 on resource_allocation should produce a warning and continue,
  never abort the whole sync. A 403 on time_card (the week cards themselves) IS fatal
  — there's nothing to show without it.
- **Row validation before any write:** task numbers match `^T[0-9A-Z]{5,30}$`;
  category values match `^[a-z0-9_ -]{2,40}$/i`; a row has either a task number OR a
  category, never both, never neither; exactly 7 day values, each a number 0-24;
  cap at 200 rows per write call. Port validWriteRows from background.js directly.
- **Two ServiceNow environments**: prod = swodp.service-now.com, UAT =
  swodpuat.service-now.com. ALL write-path testing goes against UAT first. Do not
  test POST/PATCH/DELETE against prod until reads are solid and at least one clean
  UAT write-then-verify cycle has passed.
- **Session expiry signal is UNVERIFIED** — nobody has confirmed whether an expired
  session gives a clean 401 or a 302-redirect-to-login-HTML on the Table API. Your
  first real task after the reseed check above: deliberately let a call run against
  a call after forcing/waiting out expiry (or reason about it from the SSO cookie
  lifetimes you observe) and determine what the CLI should actually detect to decide
  "reseed needed." Don't assume 401.
- **`g_ck` stability across many requests in one session is assumed but not
  stress-tested.** It held across the one authenticated test session used to
  validate this design. Verify it holds across a realistic sequence of calls
  (a full sync: history + allocations + week cards + a write) before relying on it
  for the whole CLI's lifetime-per-capture model.

## Architecture / conventions to follow

This is a NEW package in this repo (~/code/owa-tools), NOT a modification to
owa-piggy (different credential domain — ServiceNow session cookies, not AAD Graph
tokens; owa-piggy's AGENTS.md explicitly scopes it to Microsoft Graph/Outlook/Teams
and forbids other network calls — respect that boundary, don't add SWODP there).

Read this repo's own AGENTS.md (Suite Purpose, Global Contracts, Exit Codes, Shared
Contracts, Stable library-API surface, Repository Map, Verification, Workflow Rules)
and match its existing per-tool package conventions — look at src/owa_cal/ as the
closest analog (has its own profiles.py, cli.py, config under
~/.config/owa-cal/profiles.json). New package should be src/owa_swodp/ (binary name
`owa-swodp` or `swodp-cli` — check existing naming convention in Repository Map /
pyproject.toml entry points before picking).

On-disk config convention to mirror: ~/.config/owa-swodp/ (parallel to
~/.config/owa-cal/), with edge-profile/ already populated (see above) and probably a
profiles.json or similar if prod/UAT ever need to be modeled as separate "profiles"
the way owa-piggy models tenant accounts — your call based on whether one person
ever needs more than one SWODP identity (probably not — keep it simple, a single
profile is likely fine unless prod/UAT truly need independent sessions, which is
plausible since they're different ServiceNow instances entirely).

Match the suite's global contracts: JSON output by default, `--pretty` for humans,
a `status --json` health-check contract (mirrors did-cli/timereg-cli's old contract
and owa-doctor's pattern), sensible exit codes per this repo's documented scheme.

## Explicitly out of scope for this build

- The calendar-matching half of the old PoC is UNRELATED and already solved:
  `owa-cal --profile globex events --week N` replaces the entire WorkIQ +
  PowerShell + Copilot-quota dependency chain from swodp-enrichment. Don't build
  calendar fetching into swodp-cli — that's owa-cal's job already.
- Don't touch ~/code/swodp-enrichment. It's reference material for the API surface
  (background.js) and nothing else. Don't fork it, don't run its extension or app.
- Don't touch owa-piggy's package code.
- Matching/matrix logic (which calendar event maps to which SWODP activity) is a
  separate, later concern — this build is the CLI data layer (auth + read + write
  against SWODP), not the matching engine. Build the primitives first; matching can
  consume them later, potentially as a different tool or as cj-owa-tools skill logic.

## When done

Update ~/code/SKILLS-private/cj-owa-tools/SKILL.md's "Adjacent skills" / per-tool
reference section to document the new binary, following its existing per-tool
sections (see how owa-vids or owa-planner are documented for the format). Don't
invent a separate skill for it unless the surface is large enough to warrant one —
default to folding it into cj-owa-tools like the other owa-* consumer tools.
```

## Caveat

The prompt tells the fresh session the sidecar profile "already exists and is
authenticated" — true as of 2026-08-21, but Edge/ServiceNow session lifetimes are
unverified, so it may need a re-signin by the time the build session runs. The
prompt's "First step" already accounts for that gracefully.
