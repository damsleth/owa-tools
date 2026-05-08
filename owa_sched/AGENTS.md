# AGENTS.md

`owa_sched` handles free/busy, availability, and slot finding.

- Auth audience is `graph`.
- Date parsing, timezone conversion, interval math, and working-window defaults
  are high-risk.
- Do not infer write behavior; this tool should stay read-only until a plan says
  otherwise.
- Output must remain script-friendly JSON unless `--pretty` is explicit.
- Docs live in `docs/sched.md` if present; otherwise update docs before release.

Nearest tests: `tests/sched/`.

Verify:

```bash
.venv/bin/ruff check owa_sched tests/sched
.venv/bin/python -m pytest -q tests/sched
```
