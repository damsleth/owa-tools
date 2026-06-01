# AGENTS.md

`owa_sites` handles SharePoint over the **SharePoint REST API** on the
per-tenant `*.sharepoint.com` host.

- **Two audiences.** Host discovery uses a normal `graph` token
  (`GET /organization?$select=verifiedDomains`, `Organization.Read.All`) to
  derive `{initial-domain-prefix}.sharepoint.com`. The actual REST calls use a
  **SharePoint-resource token** minted via owa-piggy's `--scope` override:
  `get_token(audience='graph', scope='https://{host}/.default')`. The scope
  override wins, so the token's `aud` is the SharePoint resource
  (`00000003-0000-0ff1-ce00-000000000000`), carrying `Sites.FullControl.All` +
  `Files.ReadWrite.All`. Verified live 2026-06-01.
- **NOT the Graph `/sites` API.** The shared token lacks `Sites.Read.All`, so
  `https://graph.microsoft.com/v1.0/sites` 403s. `owa-graph sites` rides that
  dead path; owa-sites is net-new because it uses the SharePoint REST host. Do
  not "simplify" this back onto Graph `/sites`.
- Wire format is PascalCase; `sites.py` normalizes to lowercase. All requests
  send `Accept: application/json;odata=nometadata` (clean JSON, no `__metadata`).
  SharePoint's next link is the bare `odata.nextLink` (no `@`), so `paginate_sp`
  follows it itself rather than reusing `owa_core.http.paginate` (Graph's `@`).
- The tenant host is auto-discovered but can be pinned via
  `owa-sites config --host`. The site segment accepts a bare name
  (`owa-casa` -> `sites/owa-casa`), an explicit path, or empty for the root site.
- `Sites.FullControl.All` is full control (read+write+manage). **v1 is
  read-only**: `site` / `lists` / `items` / `files` / `search`. File download
  (binary `$value` -> needs `binary_stdout_commands` + `--out`) and upload
  (`Files/AddUsingPath`, destructive + confirm) are deferred to a later phase.
- Docs live in `docs/sites.md`.

Nearest tests: `src/tests/sites/`.

Verify:

```bash
.venv/bin/ruff check src/owa_sites src/tests/sites
.venv/bin/python -m pytest -q src/tests/sites
```
