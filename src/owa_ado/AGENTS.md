# AGENTS.md

`owa_ado` is a thin CLI over the Azure DevOps REST API.

- Auth audience is `devops`; the profile must broker the Azure DevOps client's
  token (owa-piggy non-FOCI capture). The FOCI Outlook client cannot mint it.
- The REST base is per-organisation (`https://dev.azure.com/<org>`), resolved
  from `--org/-o` › `OWA_ADO_ORG` › config `ado_org`. Project resolves the same
  way; every command except `projects` is project-scoped and fails fast on a
  missing project before auth.
- That scoping is the REST route, not a filter. `wi` listings build their WIQL
  without a `[System.TeamProject]` clause unless the project was named on the
  command line or in the environment, so `--mine` follows assignment across the
  whole organisation. A config-only project would otherwise hide work items
  living in any other project, which is the normal state during a board
  migration. `_project_scope` in `cli.py` owns the distinction.
- Every request carries an `api-version` query param; list endpoints page via
  the `x-ms-continuationtoken` response header, not `@odata.nextLink`.
- Work-item create/update use the `application/json-patch+json` media type
  with a list body (`owa_ado.api.json_patch`).
- WIQL has no `TOP` clause; cap with the `$top` query param on the wiql POST.
- Path segments are percent-encoded (team names contain spaces); keep `/`, `$`,
  and `:` safe so the create route `$Type` and segment separators survive.
- Mutations (`wi-create`, `wi-update`) require `--confirm` or a TTY.
- Docs live in `docs/ado.md`; update before release (CI enforces docs sync).

Nearest tests: `src/tests/ado/`.

Verify:

```bash
.venv/bin/ruff check src/owa_ado src/tests/ado
.venv/bin/python -m pytest -q src/tests/ado
```
