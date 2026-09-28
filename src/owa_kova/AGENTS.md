# AGENTS.md

`owa_kova` reads the Kova (Red Cross volunteer) schedule at `www.kova.no`.
Read-only: never sign up, cancel, or post anything without an explicit ask.

- Kova is server-rendered ASP.NET behind Okta and knows the user only by its
  session cookie. owa-piggy keeps that session in the sidecar of the profile
  with the `kova` service (`clients add kova`, renewed on reseed, session
  cookies pinned). `session.fetch_json` takes the broker's `.owa-lock`, opens
  that sidecar headless and runs `fetch()` inside the page; no cookie leaves
  the browser.
- `GetOpenDuties` returns an HTML fragment of about two months of duties.
  `schedule.parse_duties` reads names, times and flags only. The crew table
  holds other members' names and phone numbers: never emit them, and keep
  `test_parse_duties_never_carries_other_members` passing.
- The Edge/CDP helpers come from `owa_swodp`; move both into `owa_core` if a
  third sidecar tool appears.

Nearest tests: `src/tests/kova/`.

```bash
.venv/bin/ruff check src/owa_kova src/tests/kova
.venv/bin/python -m pytest -q src/tests/kova
```
