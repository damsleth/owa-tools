# AGENTS.md

`owa_places` uses the Outlook SchedulingB2 meeting-location surface, not
Microsoft Graph `/places`. It is best-effort because SchedulingB2 is an
undocumented Outlook endpoint; tolerate shape drift and keep output normalized.

Use the `outlook` audience only. Do not add Graph `Place.Read.All` scope gates.
Default output is JSON; `--pretty` is the only human-output opt-in.

Nearest tests: `src/tests/places/`.

```bash
.venv/bin/ruff check src/owa_places src/tests/places
.venv/bin/python -m pytest -q src/tests/places
```
