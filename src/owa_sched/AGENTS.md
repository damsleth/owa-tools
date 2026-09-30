# AGENTS.md

`owa_sched` handles free/busy, availability, and slot finding.

- Auth audience is `outlook` (Outlook REST v2.0 `me/calendar/getschedule`,
  `me/findmeetingtimes`). The `graph` token has no `Calendars.*` scope (403).
  Requests are PascalCase; `api.camel` lower-cases responses for the
  normalizers. `findmeetingtimes` rejects IANA zones, so its slots go in UTC.
- Date parsing, timezone conversion, interval math, and working-window defaults
  are high-risk.
- Do not infer write behavior; this tool should stay read-only until a plan says
  otherwise.
- Output must remain script-friendly JSON unless `--pretty` is explicit.
- Docs live in `docs/sched.md` if present; otherwise update docs before release.

Nearest tests: `src/tests/sched/`.

Verify:

```bash
.venv/bin/ruff check src/owa_sched src/tests/sched
.venv/bin/python -m pytest -q src/tests/sched
```
