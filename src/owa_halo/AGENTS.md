# AGENTS.md

`owa_halo` reads HaloITSM over the tenant REST API (`https://<host>/api/...`).
Read-only: never add POST/PUT/DELETE without an explicit ask.

- Auth is an owa-piggy `halo` profile (`setup --halo <host>`). The token is
  opaque (not a JWT); the host comes from the broker's `token --json` `host`
  field. `resolve_profile` picks the only Halo profile when none is given.
- `main()` passes `profile_types=('halo',)` so `-A` never reaches M365
  profiles, and M365 tools never reach Halo ones.
- Inline image URLs (`/api/attachment/image?token=`) are capability URLs.
  Never print them; `ticket.extract_images` swaps them for `halo-image:<n>`.
  Fetch them and signed CDN attachment links with
  `http.request_unauthenticated` so the bearer never leaves the Halo host.
- `GET /api/Attachment/{id}` returns `{"link": <signed url>}`, not bytes.

Nearest tests: `src/tests/halo/`.

```bash
.venv/bin/ruff check src/owa_halo src/tests/halo
.venv/bin/python -m pytest -q src/tests/halo
```
