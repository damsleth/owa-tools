# AGENTS.md

`owa_gmail` is a read-only Gmail CLI for a google-provider owa-piggy profile.

- Audience `gmail` is deliberately not an owa-piggy audience name: a Google
  profile ignores it, an AAD profile rejects it ("unknown audience"), which
  `auth.py` turns into "not a Google profile". Do not add `gmail` to
  owa-piggy's audiences.
- Fan-out and default profile ride the broker `google` service
  (`run_with_output_modes(service='google')`, `auth.resolve_profile`). No
  `command_scopes`: Google tokens are opaque, not JWTs.
- Read-only (`gmail.readonly`). Send/modify/delete need new scopes and a
  re-consent; don't add them without a plan.
- Gmail paginates with `nextPageToken` (`api.paginate`), not
  `@odata.nextLink`; `owa_core.http.paginate` does not apply.
- `format=raw` and attachments come back as base64url inside JSON;
  `messages.b64url_decode` is the only decoder. `get`/`attachments` write
  exact bytes and are `binary_stdout_commands`.

Nearest tests: `src/tests/gmail/`.

```bash
.venv/bin/ruff check src/owa_gmail src/tests/gmail
.venv/bin/python -m pytest -q src/tests/gmail
```
