# scope-aware-profile-filtering

_Created 2026-06-16_

## Goal

Stop `--profile all` (and multi-`--profile`) runs from spamming permission
errors for profiles that structurally can't perform the command. When a
profile lacks the scopes/audience a command needs (e.g. the DevOps-only
`nc-ado` profile has no mail scopes, so every `owa-mail` op against it
fails with AADSTS/403), **silently drop that profile from the fan-out**
instead of forcing the user to deactivate it.

Concrete repro: `owa-mail messages --profile all --pretty` — `nc-ado`'s
token (`aud: graph`, `scp: User.Read openid profile email ...`) carries no
`Mail.Read`, so the call always 403s. It should just not appear in the
results.

## Design constraints (from the codebase)

- Fan-out lives in `owa_core/modes.py::_run_multi_profile` (called from
  `run_with_output_modes`, which every `owa-*` binary funnels through).
  Each profile is dispatched, and `OwaError` is already caught per-profile
  into a `records[]` entry with `ok/rc/error`. This is the natural place to
  insert a pre-flight skip.
- Each tool already declares its target via `AUDIENCE` in
  `<tool>/auth.py` (e.g. `owa_mail/auth.py: AUDIENCE = 'outlook'`). There is
  **no per-command required-scope table yet** — that's the new thing to add.
- `owa_core/jwt.py` already has `scopes_in_token()` and `scope_in_token()`
  (reads `scp`/`roles` from the JWT, advisory not authoritative) and
  `decode_token_audience()`. `TokenResult` (auth.py) carries `.scope` and
  `.audience`. So once a token is in hand the check is trivial — the only
  cost is acquiring it.
- `get_token_for_config(config, tool_name, audience, scope=...)` brokers a
  token via owa-piggy. The broker caches, so acquiring just to read scopes
  is cheap-ish but not free; prefer reading a cached token where possible.

## Key decision: silent skip ONLY for fan-out

- `--profile all` / multi-`--profile`: missing-scope profiles are **silently
  dropped** (default). They don't appear in `records[]` at all (or appear
  with a `skipped: "missing-scope"` marker — see open question).
- A **single explicitly-named** `--profile nc-ado`: do NOT silently swallow.
  Either run as today (let the 403 surface) or emit a clear
  "profile lacks scope X for this command" usage error. Explicit intent
  must never be silently no-op'd.

## Status — IMPLEMENTED 2026-06-16

Shipped the core mechanism + wired the four scope-differentiated tools.
Decisions made (overriding the open questions below):

- **Acquire, don't error-classify.** Per the user, the filter mints a token
  per profile (broker caches, so dispatch's re-mint is cheap) and reads its
  scopes — keeping fresh tokens warm is a goal anyway. No AADSTS string
  matching.
- **`--profile all` only.** Filtering is gated on `all_requested`; explicit
  `--profile X [--profile Y]` is never filtered and still errors, since
  naming a profile is an explicit request to run against it.
- **Any-of, lenient.** `command_scopes[cmd]` is the set of scopes that grant
  the command; a profile is kept if its token's scope set intersects that set
  (or dropped if the audience token can't be minted at all). Lenient by
  design — a partial match keeps the profile rather than silently dropping
  data; worst case the old error surfaces for that one profile.
- **Skip visibility:** silent in normal output; `--debug` logs
  `skip profile 'x': cannot mint <aud> token` / `... lacks required scopes`.

Implemented:
- `owa_core/modes.py`: `run_with_output_modes(..., audience=, command_scopes=)`
  → threaded into `_run_multi_profile` with `all_requested`; new
  `_filter_profiles_by_scope()` helper.
- Wired: `owa-mail` (outlook/Mail.*), `owa-cal` (outlook/Calendars.*),
  `owa-drive` (graph/Files.*+Sites.*), `owa-sched` (graph/Calendars.Read).
- **Deliberately NOT wired:** `owa-graph` (raw REST, dynamic per-call
  audience — wrong fit for a static command→scope table); `owa-people`
  (gates on `User.Read`, which nearly every token carries → low value, real
  false-skip risk).
- Tests in `src/tests/core/test_modes.py` (skip-on-missing-scope,
  skip-on-unmintable, explicit-multi-not-filtered, unlisted-command-not-
  filtered, debug logging). Full suite 2222 passed; coverage 90.17% (gate 89).

## Steps (original)

- [x] Add a per-command required-scope declaration mechanism. Chose option
      (a): a `command_scopes` dict per tool + `audience=`, passed as kwargs to
      `run_with_output_modes` (matches the existing `binary_stdout_commands=`
      style). Original options were:
      (a) a module-level dict in each tool's `cli.py` mapping command →
      required scope set, passed into `run_with_output_modes` as a new
      `required_scopes=` kwarg; or (b) a `requires=` decorator/attr on each
      command handler. Lean toward (a) — explicit, central, testable, and
      matches the existing `binary_stdout_commands=`/`interactive_commands=`
      kwarg style of `run_with_output_modes`.
- [ ] Decide scope granularity: audience-level (cheap, coarse — "does this
      profile even have an `outlook`/`graph` token?") vs scope-level
      (precise — `Mail.Read` for read, `Mail.Send` for send). Recommend
      starting audience+coarse-scope (one representative scope per command)
      and refining later; the JWT helpers already support both.
- [ ] Implement the pre-flight check in `_run_multi_profile`: for each
      profile, resolve its token's scope set (via cached token / a light
      broker call), compare against the command's required set using
      `scopes_in_token`. On miss → skip the profile (don't dispatch).
- [ ] Handle the "no scopes known without acquiring a token" reality: the
      broker must mint/return a token to read its `scp`. Decide whether the
      pre-check acquires (and caches) the token, or whether we let dispatch
      run and instead classify the resulting AADSTS/403 error as
      "missing-scope → drop from fan-out" rather than "failure". The
      error-classification route avoids an extra token acquisition and may
      be the pragmatic MVP. (See open questions.)
- [ ] Wire required-scope tables into the scope-heavy tools first:
      `owa-mail` (Mail.Read / Mail.Send / Mail.ReadWrite), then `owa-cal`,
      `owa-people`, `owa-drive`, `owa-graph`. Tools where every profile is
      expected to work (e.g. `owa-doctor`) need no table.
- [ ] Surface what was skipped without being noisy: when `--debug`, log
      `skipped <profile>: missing <scope>`; in normal output, omit entirely
      (or include a compact `skipped` list in the JSON meta so automation
      can see it). Don't print warnings to stderr by default.
- [ ] Tests: a fan-out where one profile lacks scopes drops silently and the
      remaining profiles still return; an explicitly-named scope-lacking
      profile still errors (or warns) rather than silently no-op'ing;
      `--debug` reports the skip. Mind the ~0-slack 90% coverage gate
      (see owa-tools-release-gotchas memory).

## Open questions (resolve before implementing)

1. **Pre-flight acquire vs error-classify?** Acquiring every profile's token
   up front to read scopes is the "clean" check but costs broker round-trips
   for profiles we're about to skip. Classifying the post-dispatch
   AADSTS65002/403 as "missing-scope → drop" is cheaper and reuses tokens
   that have to be minted anyway, but couples filtering to error-string
   matching. **Recommend error-classify for MVP, pre-flight table as the
   refinement.**
2. **Skip marker visibility:** fully invisible, or a `skipped: [...]` array
   in JSON meta + `--debug` log line? Recommend the latter — silent in
   pretty/human output, discoverable in JSON/debug.
3. **Single explicit profile behavior:** silent today's-403, or a friendly
   "this profile can't do that" usage error? Recommend the friendly error.
4. **Scope source of truth:** a profile's *current* token scopes (what
   owa-piggy minted) vs the audience's *maximal* possible scopes. A profile
   might be able to consent to more than its current token shows. For the
   "is this fan-out worth attempting" question, current-token scopes are the
   right signal.

## Notes

- This is a `owa_core` change with per-tool opt-in tables — additive, no
  breaking behavior for single-profile runs (which already pass argv through
  untouched on the N<=1 byte-identical path).
- The example token in the request is the `nc-ado` Azure DevOps profile:
  `aud: https://graph.microsoft.com`, `scp: CrossTenantInformation.ReadBasic.All
  email openid profile User.Invite.All User.Read` — no mail/cal scopes, which
  is exactly the class of profile that should be auto-skipped by owa-mail/-cal.
