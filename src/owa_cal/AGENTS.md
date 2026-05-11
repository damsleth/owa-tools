# AGENTS.md

`owa_cal` handles calendar and webcal behavior.

- Outlook REST auth audience is `outlook` for OAuth calendar calls.
- Webcal profiles are local and read-only; they must not hit OAuth write paths.
- Date windows, time zones, DST boundaries, and ICS output require focused
  tests.
- Mutating calendar commands must be explicit about confirmation and retry
  safety before release.
- Docs live in `docs/cal.md`.

Nearest tests: `src/tests/cal/`.

Verify:

```bash
.venv/bin/ruff check src/owa_cal src/tests/cal
.venv/bin/python -m pytest -q src/tests/cal
```
