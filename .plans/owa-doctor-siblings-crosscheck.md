# owa-doctor-siblings-crosscheck

> **Status: DONE** — shipped in `b290aa1` (2026-05-29),
> `test(doctor): cross-check siblings[] against per-binary --doctor schema`.
> `tests/doctor/test_cli_report.py` now carries `_DOCTOR_PAYLOAD_SCHEMA`,
> `_assert_doctor_payload`, and the parametrized
> `test_siblings_match_per_binary_doctor` (`pytest.skip` when a binary is off
> PATH). See [DONE.md](DONE.md).

_Migrated 2026-05-29 from `hugr/.plans/` — this is owa-tools-local test work, so
it belongs here, not in the hugr repo. (hugr only consumes `owa-doctor`'s
aggregate output and never imports owa-tools — the loose-coupling axiom.)_

> **Stale-reference note:** the original plan cited `AUDIT.md` (item 9, lines
> 132-136 and the sibling roster at line 54). That file was **retired** in hugr
> (commit `2f6782a`, 2026-05-29). The cross-check below is self-contained;
> source the real payload shapes from the binaries themselves, not from the
> dead AUDIT.md.

## Goal

`owa-doctor` aggregates each sibling binary's self-diagnostic into a
`siblings[]` array. Today's test (`tests/doctor/test_cli_report.py`) pins the
*aggregate* `build_report()` shape but never verifies that each `siblings[]`
entry actually matches what that binary emits when you run `<binary> --doctor`
directly. Drift between the two (a field renamed in one binary, a schema
version bump) would go uncaught. Add the cross-check.

## The cross-check to add

For every sibling binary in the aggregator (`owa`, `owa-cal`, `owa-mail`,
`owa-graph`, `owa-doctor`, `owa-people`, `owa-sched`, `owa-drive`, `owa-todo`),
assert that the corresponding `siblings[]` entry in `owa-doctor --json` is
**schema-compatible with** that binary's own `<binary> --doctor --json`
payload:

- Same set of required keys (e.g. `tool`, `ok`, `version`, `checks[]` — confirm
  the actual field names from the real payloads).
- Same types per key.
- The aggregated entry is allowed to be a *subset* (aggregator may drop verbose
  fields) but must not *rename* or *retype* anything it keeps.

Encode the shared schema once and assert both the per-binary payload and the
aggregated entry conform to it, so the test fails if *either* side drifts.

## Steps

- [x] Locate `tests/doctor/test_cli_report.py` and the `build_report()`
      implementation it covers. Identify how `siblings[]` entries are
      constructed (which binaries, which fields are copied vs. summarized).
- [x] Define the canonical sibling-entry schema (a dict of `key -> type`, or a
      Pydantic model / jsonschema if owa-tools already uses one). Source it from
      the real payloads — run `owa-cal --doctor --json` etc. and read the actual
      shape. _Shipped as `_DOCTOR_PAYLOAD_SCHEMA` + `_assert_doctor_payload`._
- [x] Add `test_siblings_match_per_binary_doctor`: for each sibling, (a) invoke
      `<binary> --doctor --json` (skip if not on PATH), (b) pull the matching
      entry from `owa-doctor --json`'s `siblings[]`, (c) assert both conform to
      the schema and that the aggregated entry's kept keys equal the per-binary
      values for a stable field (e.g. `tool`, `version`).
- [x] Gate on availability: `pytest.skip` when a sibling binary isn't installed,
      so the test is green in minimal CI.

## Open question

- **Is `owa-doctor` invoked as a subprocess or imported in the test?** Lean:
  import `build_report()` directly for the aggregate (fast, deterministic,
  already the pattern in `test_cli_report.py`), and shell out to the individual
  `<binary> --doctor --json` for the per-binary side (the real contract). Stay
  consistent with how `test_cli_report.py` does it today.

## Notes

- Self-diagnostic payload contract and the `siblings[]` shape live in this
  repo's conventions (`src/owa_core/conventions.py`) and `AGENTS.md`. Check the
  `CANARY_SECRET_xxxx` redaction-fixture pattern if any doctor field could carry
  secrets.
- Small; could be batched with any other owa-tools work rather than done
  standalone.
