# AGENTS.md

`owa` is the umbrella discovery and orchestration binary.

- Keep it small: list tools, show suite version, expose schema, and forward
  doctor checks.
- Resolve sibling binaries from the active install before falling back to PATH.
- Do not turn this into a full command proxy unless the plan is updated first.
- Output contracts match every other CLI: JSON stdout, diagnostics stderr.

Nearest tests: `src/tests/contract/`, `src/tests/compat/`.

Verify:

```bash
.venv/bin/python -m pytest -q src/tests/contract tests/compat
```
