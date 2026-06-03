# AGENTS.md

`owa_vids` downloads Microsoft Teams / OneDrive meeting-recap video streams
(DASH manifest -> clear fmp4 segments -> `ffmpeg -c copy` mux).

- Auth is two-audience: a SharePoint resource token for the svc.ms manifest
  and segments (minted as `audience=graph` + `--scope https://{spo_host}/.default`,
  same mechanism as `owa_sites` - there is no named `spo` audience), plus a
  plain `graph` token for identity resolution and title fetch. The SPO host
  comes from the source URL at runtime, so there is no `API_BASE` constant
  and auth is deferred into each command handler.
- The segment download loop (`segments.py:download_track`) uses
  `owa_vids.http.Http` (per-host persistent keep-alive) rather than
  `owa_core.http` - this is intentional; the svc.ms CDN throttles reconnects.
  Do not refactor onto `owa_core.http` without re-testing against a live
  svc.ms tenant.
- No writes to SharePoint. All operations are read-only (GET + ffmpeg mux to
  a local file). No `--confirm` machinery needed.
- ffmpeg is an external runtime requirement for `get` only (checked with a
  `shutil.which` guard before any download starts).
- The AES-CBC decryption fallback from the standalone repo (`recap-dl.py`)
  is explicitly NOT part of this package. `parse_manifest` rejects encrypted
  manifests with a UsageError. Do not add decryption.
- Docs live in `docs/vids.md`.

Nearest tests: `src/tests/vids/`.

Verify:

```bash
.venv/bin/ruff check src/owa_vids src/tests/vids
.venv/bin/python -m pytest -q src/tests/vids
```
