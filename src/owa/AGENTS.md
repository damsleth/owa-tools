# AGENTS.md

`owa` is the umbrella binary: suite discovery plus pass-through dispatch.

- Meta commands operate on the suite as a whole: `owa list`, `owa schema`,
  `owa version`, and the `owa --doctor` flag. Keep these small.
- Tool dispatch: `owa <tool> [args...]` forwards everything after the tool
  name to `owa-<tool>`'s `main(argv)` **in-process**. All tools ship in this
  one distribution, so the package is always importable when `owa` is; no
  subprocess. The tool wraps its own dispatch in `run_with_output_modes`, so
  `--agent`/`--err-json`/`--doctor` and the exit-code taxonomy pass through
  unchanged.
- Do NOT re-declare any tool's flags, help, or schema here. The tool owns its
  own `--help`, `--version`, and `schema`; `owa` only routes argv.
- `TOOL_PACKAGES` is derived from `CONSUMERS` so the dispatch table never
  drifts from the discovery list. Both short (`cal`) and binary (`owa-cal`)
  forms resolve. `owa doctor` dispatches to `owa-doctor`, which defaults to
  `probe` on its own — `owa` no longer inserts the `probe` subcommand.
- Meta-command names must never collide with a tool short name; dispatch only
  runs when the first arg is not a meta command.
- `owa list`/`owa schema` still shell out to the sibling binaries for
  discovery/aggregation; resolve them from the active install before PATH.
- Output contracts match every other CLI: JSON stdout, diagnostics stderr.

Nearest tests: `src/tests/owa/`, `src/tests/contract/`, `src/tests/compat/`.

Verify:

```bash
.venv/bin/python -m pytest -q src/tests/owa src/tests/contract src/tests/compat
```
