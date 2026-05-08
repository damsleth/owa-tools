# AGENTS.md

Ground rules for any contributor (human or model) working in `owa-tools`.

## Suite invariants

- **Stdlib only at runtime.** No `requests`, `msal`, `pydantic`, `rich`, `click`, or Microsoft SDKs. The only allowed non-stdlib runtime imports are the `owa_*` consumer packages in this repo, and `owa-piggy` via subprocess. Enforced by `tools/check_stdlib_only.py` in CI.
- **JSON on stdout, logs on stderr.** Every command emits machine-readable JSON to stdout by default. Diagnostics, prompts, and warnings go to stderr. `--pretty` switches stdout to a human render.
- **Auth via `owa-piggy`.** No CLI in this suite stores a refresh token. Each invocation shells out to `owa-piggy token --json --audience <X>`.
- **Profiles are forwarded, not duplicated.** `--profile <alias>` resolves inside `owa-piggy`. Consumers know only the alias name.
- **No telemetry.** No update checks. The only outbound HTTP is Microsoft Graph / Outlook REST, plus `login.microsoftonline.com` indirectly via `owa-piggy`.

## Agent contract

Every consumer CLI in this repo upholds the same machine contract:

1. **Stdout = JSON by default.** Inviolable.
2. **Stderr is for humans and diagnostics only.** No JSON envelopes on stderr.
3. **Stable exit-code taxonomy.**
   - `0` success
   - `2` usage error
   - `10` network error
   - `11` auth expired
   - `12` auth scope insufficient
   - `13` not found
   - `14` rate-limited (after retries)
   - `15` conflict / precondition failure
   - `20` internal error
   - Per-tool exceptions (e.g., `owa-doctor probe` `0/1/2`) are documented at the command level.
4. **No prompts when stdin is not a TTY.** Destructive commands require explicit `--confirm` or `--yes` off-TTY. Otherwise exit `2` with a clear hint.
5. **Idempotency where the API supports it.** Document retry safety per command. Add `--idempotency-key` only where the backing API can honor it.

## Coding style

- Two-space indentation in shell and docs. Four-space indentation in Python (PEP 8).
- No semicolons in JS/TS.
- No emoji, no emdash. Use a regular dash.
- Comments only when the *why* is non-obvious. Code comments should not narrate.

## Workflow rules

- **Never modify `owa-piggy` from this repo.** It lives in its own repository.
- **No new third-party runtime imports.** Period.
- **Per-tool semver.** Tags are `<tool>-vX.Y.Z`.
- **One package per PR where possible.** Keeps reviews scoped.
