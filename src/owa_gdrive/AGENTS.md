# AGENTS.md

`owa_gdrive` is a read-only Google Drive CLI for a google-provider owa-piggy
profile. OneDrive is `owa_drive`; keep the two apart.

- Audience `gdrive` is deliberately neither `drive` (owa-drive) nor a real
  owa-piggy audience: an AAD profile rejects it, which `auth.py` turns into
  "not a Google profile". Fan-out and the default profile ride the broker
  `google` service via `owa_core.auth.resolve_service_profile`.
- Read-only (`drive.readonly`). Writes need `drive.file` (not `drive`) and a
  re-consent; don't add them without a plan.
- Google-native files have no content: `alt=media` is a 403. `get` reads the
  mime type first and exports via `files.resolve_export_mime`. Content
  endpoints return raw bytes (unlike Gmail's base64-in-JSON).
- No paths (Drive has only parent ids); a bare `ls` means `'root' in parents`,
  not the whole Drive. Drive query literals escape `'` as `\'`, not `''`.
- Paging is `owa_core.http.paginate_by_token` (shared with owa_gmail).

Nearest tests: `src/tests/gdrive/`.

```bash
.venv/bin/ruff check src/owa_gdrive src/tests/gdrive
.venv/bin/python -m pytest -q src/tests/gdrive
```
