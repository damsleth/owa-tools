# multi-profile simultaneous calls

_Created 2026-06-01 · Foundation shipped in v0.6.1 (2026-06-02)_

> **Status:** the fan-out **foundation** is implemented, tested, and released
> in v0.6.1. Key deviation from the original design: rather than wiring each
> tool's dispatcher, the entire fan-out lives in the shared
> `owa_core.modes.run_with_output_modes` entry point that all 11 CLIs already
> route through — so every tool (incl. planner/sites/todo) gained repeated
> `--profile` with **zero per-tool code**. `owa-doctor` opts out
> (`fan_out_profiles=False`). Remaining follow-up: per-command `--help` text,
> prose docs (`docs/profile-model.md` et al.), and broader per-tool
> integration tests.

Let owa-* verbs accept **repeated** `--profile` flags and run the same command
against each profile in one invocation, fanning out auth + execution and merging
the results.

```
owa-graph GET /me --profile crayon --profile brkh
owa-drive ls --pretty --profile crayon --profile swon
owa-mail  tui          --profile crayon --profile swon
```

## Goal

A single `--profile X --profile Y …` call fans out across all named profiles,
acquires a token per profile, runs the verb once per profile, and emits results
keyed by profile. Single-`--profile` and zero-`--profile` behaviour stays
byte-identical (no regression for the common case).

## Current state (from survey)

- **No shared arg parser.** Each tool manually loops `sys.argv` and extracts
  `--profile` as a *global* flag (owa-doctor is the exception: per-subcommand).
  - owa-graph `src/owa_graph/cli.py:732-776`
  - owa-cal `src/owa_cal/cli.py:1033-1069`
  - owa-drive `src/owa_drive/cli.py:550-583`
  - owa-mail `src/owa_mail/cli.py:48-79` (`_split_globals` — cleanest)
  - owa-people / owa-sched — same pattern
  - owa-doctor `src/owa_doctor/cli.py:81-112` (per-command)
- Today `--profile` sets `config['owa_piggy_profile']` (single string).
- Profile→token: `owa_core.auth.get_token_for_config(config, …)` reads that key
  and shells `owa-piggy token --profile <alias> --json`
  (`src/owa_core/auth.py:109-160`).
- Output: raw JSON default; `--pretty` tables; `--ndjson`; agent envelope
  `{"_owa": {...}, "data": ...}` from `src/owa_core/modes.py:42-54`
  (envelope reads profile from `OWA_PROFILE` env only).
- TUI: `src/owa_mail/tui.py` is curses-based, bound to one token/api_base set at
  launch; no mid-session profile switch. Marked `interactive=True`, refused under
  `--agent` (`modes.py:119-128`).

## Design decisions

1. **Profiles are a list.** Introduce `config['owa_piggy_profiles']` (list[str]);
   keep `owa_piggy_profile` as the single/first value for back-compat with every
   existing `get_token_for_config` caller. Empty list ⇒ default profile (unchanged).
2. **Fan-out lives in `owa_core`, not per-tool.** Add a shared helper so each
   tool's dispatcher stays thin and behaviour is uniform. Tools opt in by routing
   their "run the command body" through it.
3. **Order + de-dup.** Preserve flag order; de-dup repeats (warn on dupes).
4. **Per-profile isolation.** One profile's auth failure or error must not abort
   the others — collect `{profile, ok, data|error}` per profile.
5. **Output shape for N>1.** Wrap in a multi-profile envelope:
   `{"_owa": {... "profiles": [...]}, "results": [{"profile": "crayon", "ok": true, "data": ...}, ...]}`.
   N==1 ⇒ **unchanged** legacy shape (no `results` wrapper) to avoid breaking
   scripts. `--pretty` ⇒ one labelled section per profile.
6. **TUI is special.** A single curses screen can't be two profiles at once.
   Decide between: (a) refuse `tui` with >1 profile (fast, safe first cut),
   (b) profile-switcher hotkey, (c) merged/tabbed inbox. Ship (a) first; file
   (b)/(c) as follow-ups.

## Steps

- [x] **`owa_core` — profile list parsing.** `parse_profiles(argv) ->
  (profiles, rest_argv)` shipped in new `owa_core/profiles_args.py`. Collects
  every `--profile`/`-p` (+`=` form), de-dups preserving order, warns on dupes.
  _Note: no `config['owa_piggy_profiles']` key — the fan-out runner appends a
  single `--profile <p>` per iteration so each tool's existing single-profile
  parse populates `owa_piggy_profile` unchanged._
- [x] **`owa_core.auth` — no breaking change.** `get_token_for_config` untouched;
  each fan-out run sets one `owa_piggy_profile` via the tool's own parse.
- [x] **`owa_core` — shared fan-out runner.** Shipped as
  `_run_multi_profile` + `_multi_exit_code` inside `modes.run_with_output_modes`
  (not a standalone `run_across_profiles`). `len<=1` ⇒ original argv passed
  through untouched (byte-identical); else per-profile capture/isolation + §5
  envelope with `profiles` in meta.
- [x] **Wiring — done in the shared layer instead of per-tool.** All 11 CLIs
  already route through `run_with_output_modes`, so none needed dispatcher
  edits. `owa-doctor` opts out via `fan_out_profiles=False` (it already probes
  every profile in one pass). _Remaining: each tool's `--help` text still
  doesn't advertise the repeatable flag (see Docs)._
- [x] **Pretty / ndjson for N>1.** `=== profile: <name> ===` sections (+`(FAILED)`
  line); `--ndjson` emits `{"profile":…, "item":…}` per line. N==1 unchanged.
- [x] **owa-mail tui.** Interactive commands are refused generically for >1
  profile in the shared runner (no per-tool `cmd_tui` change). Tabs/switcher
  still a future follow-up.
- [x] **Exit codes.** all ok ⇒ 0; mixed ⇒ 2; all fail ⇒ 1. _Not yet in `--help`._
- [~] **Tests.** Done: `parse_profiles` (none/one/many/dupes/`-p`/`=`/dangling),
  fan-out isolation, **golden no-regression** (fan-out on/off byte-identical for
  N<=1), N>1 JSON/pretty/ndjson, interactive+binary refusal, doctor opt-out.
  _Pending: per-tool end-to-end integration tests with mocked auth._
- [ ] **Docs.** Pending: each tool's `--help`, suite README, `docs/profile-model.md`
  + per-tool docs, AGENTS reference, and cj-owa-tools skill notes; note
  `OWA_PROFILE` vs repeated `--profile` (flag wins; env is single fallback).

## Notes

- **N==1 must not regress.** The back-compat story hinges on "1 profile ⇒ old
  shape". Lock with golden tests before touching formatters.
- **Concurrency:** sequential first (simpler, deterministic output). A
  `--parallel` opt-in can come later — but owa-piggy interactive auth prompts
  would interleave badly under parallel, so keep serial by default.
- **Per-profile audiences differ** (memory: `outlook` token huge, `graph`
  narrower; CA policy varies per profile). Fan-out must tolerate one profile
  lacking scope/consent while others succeed (§4 isolation covers it).
- **Aliases:** crayon/brkh/swon are owa-piggy aliases; no change to alias
  resolution — pass each through unchanged.
- **TUI multi-profile** is the only genuinely hard verb; everything else is
  fan-out + merge. Don't let it block the rest — ship refusal, iterate later.
