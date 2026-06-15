# owa suite-wide "all profiles" fan-out

_Created 2026-06-15_

## Goal

Let any owa-* command fan out across **every** stored profile in one shot,
instead of repeating `--profile a --profile b --profile c`. Same result shape
as the existing multi-`--profile` fan-out (records keyed by profile), just with
the profile list auto-resolved from the broker registry.

Target spellings (all equivalent):
- `--profile all`  ← canonical meta-profile
- `-A`             ← short alias
- `--all-profiles` ← long alias

e.g. `owa-cal events --pretty --profile all`, `owa-graph GET /me -A`,
`owa-mail messages --all-profiles`, `owa-todo tasks -A`.

## Collision analysis (DONE — this was the gating question)

Audited `src/` for each proposed spelling:

| Spelling          | Collides? | Evidence |
|-------------------|-----------|----------|
| `--all`           | **YES — hard collision** | `--all` is the **pagination** flag suite-wide: "Follow @odata.nextLink / continuation tokens until exhausted." Used in `owa_graph/cli.py`, `owa_mail/cli.py` (×3), `owa_people/cli.py` (×2), `owa_ado/cli.py`. Declared as `schema_mod.flag('--all', ...)` and matched via `elif flag == '--all'`. Reusing it for profile fan-out would be ambiguous and break every paginating command. **Rejected.** |
| `--all-profiles`  | No        | No occurrences anywhere in `src/`. Distinct token; flags are matched by exact string (`elif flag == '--all'`), so no prefix bleed with `--all`. Safe. |
| `-A`              | No        | No `-A` short flag exists anywhere (only `-p`, `--retry`, etc.). Safe. |
| `--profile all`   | No        | `--profile`/`-p` already parsed by `owa_core/profiles_args.py:parse_profiles`. `all` is just a reserved **value**, not a new flag. Cleanest — reuses the entire existing fan-out path. Only risk: a real profile literally named `all` (guard below). |

**Decision:** ship `--profile all` as canonical, with `-A` and `--all-profiles`
as aliases that normalize to the same internal "expand to all profiles" signal.
Do **not** introduce bare `--all`.

## How the existing fan-out works (reuse this — don't reinvent)

- `owa_core/modes.py:run_with_output_modes(..., fan_out_profiles=True)` is the
  shared entry every tool routes through (`owa_*/cli.py` all
  `from owa_core import modes as mode_mod`).
- It calls `parse_profiles(filtered)` (`owa_core/profiles_args.py`) to pull
  repeated `--profile`/`-p` values out of argv → `(profiles, rest)`.
- If `len(profiles) > 1` → `_run_multi_profile(...)` runs `dispatch` once per
  profile (appending one clean `--profile <p>` each), captures stdout per run,
  and merges into json / `_emit_multi_pretty` / `_emit_multi_ndjson`, with
  `_multi_exit_code` (0 all-ok, 1 all-fail, 2 partial).
- Profile registry is already available: `owa_core/auth.py:get_profiles(tool_name=...)`
  shells `owa-piggy profiles --json` → `[BrokerProfile(alias, default, registered, has_config)]`.

So the feature is essentially: **resolve the "all" sentinel into the concrete
alias list before the `len(profiles) > 1` check**, and everything downstream
(capture, merge, pretty/ndjson, exit codes, agent-mode refusals for
interactive/binary commands) works unchanged.

## Steps

- [ ] **1. Normalize the alias flags → meta-profile token.** In `split_mode_flags`
  (or a small new helper in `modes.py`, kept next to it), strip `-A` and
  `--all-profiles` from argv and treat them as if `--profile all` were present.
  Keep this tool-agnostic so all 13 binaries inherit it for free. Make it
  idempotent (multiple aliases + explicit `--profile all` collapse to one).
- [ ] **2. Teach the dispatcher about the `all` sentinel.** Keep `parse_profiles`
  purely syntactic; add an `expand_all_profiles(profiles, *, tool_name)` step in
  `run_with_output_modes` that, when the literal `all` appears among the parsed
  profile values, replaces it by calling `get_profiles(tool_name=tool)` and
  substituting every `alias`. De-dup while preserving order; drop the `all` token.
- [ ] **3. `all` is a RESERVED name — hard error, never a warning.** A profile
  literally named `all` is forbidden. At **run time**, if `get_profiles()`
  returns an alias `all` (i.e. someone hand-edited the broker store instead of
  going through the CLI), raise a typed `UsageError` ("`all` is a reserved
  meta-profile name; rename this profile") and exit non-zero — do not expand, do
  not shadow-silently. Mirror the same rejection at **creation** time in
  owa-piggy (separate repo — file as a follow-up so both ends enforce it).
- [ ] **4. Empty / single-profile edge cases.**
  - 0 eligible profiles → typed `UsageError` ("no active profiles; run
    owa-piggy login"), non-zero exit. Never silently no-op.
  - **N==1 from the `all` sentinel still goes through the multi path** (see
    step 5 for the rationale): the output shape must not depend on how many
    profiles happen to exist. Legacy explicit single `--profile a` stays on the
    byte-identical single path, unchanged.
- [ ] **5. One stable contract: "fan-out requested" → keyed records, always.**
  Decision (low entropy + agent discoverability): the *shape* of the output is a
  function of **intent**, not of profile count. Carry an `all_requested` boolean
  from normalization (set when `all`/`-A`/`--all-profiles` was used) and gate as
  `if all_requested or len(profiles) > 1: _run_multi_profile(...)`. So
  `--profile all` always yields the profile-keyed record shape — even for a
  single profile — eliminating the "array of length 1 vs scalar" edge case an
  agent would otherwise have to special-case. Legacy `len > 1` behavior is
  untouched; a lone explicit `--profile a` still gets the flat byte-identical
  path. Net: exactly two code paths, each with a clear, count-independent
  contract — no third special case introduced.
- [ ] **6. Respect existing fan-out guards.** `_run_multi_profile` already refuses
  `interactive_commands` (TUIs) and `binary_stdout_commands` (`--out` downloads)
  with typed errors. "all" expansion routes through the same gate, so those cmds
  get the existing refusal for free — just verify the messages read sensibly.
- [ ] **7. "all" scope = active + configured only.** Include a profile iff it is
  **active/registered AND has config**; skip config-less and inactive profiles
  entirely (don't even warn-spam per skip — they're simply not part of "all").
  Verify the exact `BrokerProfile` field mapping in `owa_core/auth.py`
  (`registered`, `has_config`) covers "active" + "configured"; if "active" needs
  a distinct signal not currently surfaced by `owa-piggy profiles --json`, add it
  to the broker payload as a follow-up rather than guessing. Keep the eligibility
  predicate in one helper so the policy lives in exactly one place.
- [ ] **8. Help text + completions (progressive disclosure).** Add `--profile all`
  / `-A` / `--all-profiles` to each tool's `--help` epilog (the `--profile` line),
  to `src/completions/owa-*.bash` + `owa-*.zsh` (offer `all` as a `--profile`
  value), and to `docs/` + `README.md` where multi-profile fan-out is documented.
  Surface `all` at the `--profile` line, not as a separate concept — it reads as
  a natural extension of the flag the user already knows.
- [ ] **9. Schema/agent surface.** Ensure the envelope advertises the resolved
  concrete `profiles` list (it already passes `profiles` to `_emit_multi_json`),
  so agent consumers see expanded aliases, not the literal `all`.

## Tests

- New core unit tests (alongside existing modes/profiles tests):
  - `-A`, `--all-profiles`, `--profile all` all normalize to the same expanded list
  - expansion calls `get_profiles` once, de-dups, preserves order
  - 0 eligible profiles → UsageError
  - **N==1 via `all` → still keyed multi-record shape** (not flat); legacy lone
    `--profile a` → flat byte-identical path
  - config-less / inactive profiles excluded from "all"
  - real profile named `all` → hard `UsageError` (reserved name), non-zero exit
  - interactive/binary command + `--profile all` → existing refusal fires
- Per-tool smoke (mirror `tests/mail/test_cli_all_pagination.py` patterns, but for
  profile fan-out): assert merged record shape keyed by each alias.
- Mock `owa-piggy profiles --json`; don't hit the real broker in tests.
- **Coverage gate is 90% with ~0 slack** (memory: `owa-tools-release-gotchas`) —
  run `pytest` + coverage locally before declaring done.

## Decisions (resolved 2026-06-15)

- Canonical spelling = `--profile all`; `-A` + `--all-profiles` are aliases.
  Bare `--all` deliberately NOT used (pagination collision).
- **`all` is reserved** — hard error (not a warning) both on creation (owa-piggy
  follow-up) and at run time if a hand-created profile is named `all`.
- **"all" scope** = active/registered **AND** configured profiles only;
  config-less and inactive are silently excluded (they're not part of "all").
- **Output shape follows intent, not count**: `--profile all`/`-A`/`--all-profiles`
  always yields profile-keyed records, even for N==1 — no length-1 edge case.
  Legacy lone `--profile a` stays flat/byte-identical. Two code paths, two clear
  contracts.
- Release: bump version + `test_version.py`, update CHANGELOG.

## Open follow-ups (separate repo / later)

- owa-piggy: reject `all` as a profile alias at creation time.
- owa-piggy: confirm `profiles --json` distinguishes "active" from merely
  "registered"; if not, add the signal so step 7's predicate isn't a guess.
