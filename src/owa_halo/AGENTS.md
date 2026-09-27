# AGENTS.md

`owa_halo` reads HaloITSM over the tenant REST API (`https://<host>/api/...`).
Read-only: never add POST/PUT/DELETE without an explicit ask.

- Auth is the `halo` service on an owa-piggy profile (`owa-piggy clients add
  halo=https://<host> --profile nc`; the broker captures Halo's refresh token
  from the profile's Edge sidecar). `token --audience halo --json` returns an
  opaque bearer (not a JWT) plus the tenant `host`. `resolve_profile` takes
  `--profile`, else the default profile if it has `halo`, else the only one.
- `main()` passes `service='halo'` so `-A` only reaches profiles with Halo.
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
