# Plan: `owa-gmail` (Gmail read CLI)

Status: planning only, nothing implemented yet.

## Context

owa-piggy grew a second auth provider (`OWA_PROVIDER=google`) so a profile can
be a real Google OAuth client instead of a piggybacked MSAL client. A live
profile (`brkh-g`, BRKH Workspace account) already mints working Gmail-scoped
access tokens via `owa-piggy --profile brkh-g token --audience gmail --json`.

The point of that work was to let `owa-tools` consumer CLIs stay exactly as
auth-dumb as they are today: get a token from `owa-piggy`, call the API, print
JSON. This plan is that consumer for Gmail. It exists so YAAMS can eventually
add a `gmail_mail.py` ingester that shells out to `owa-gmail` the same way
`yaams/ingest/m365_mail.py` shells out to `owa-mail` today - this tool is not
YAAMS-specific, but that's the motivating first consumer.

**Naming**: the working name was "gmail-cli"; the actual deliverable follows
the suite's `owa-*` convention exactly, like every other tool in this repo.
Binary: `owa-gmail`. Package: `owa_gmail`. Audience string passed to
owa-piggy: `gmail` (chosen deliberately - see "Auth" below for why an
unclaimed, Gmail-specific string is the *correct* choice, not a placeholder).

**Scope for v1**: read-only. The Google OAuth client only has
`gmail.readonly` consented (see owa-piggy's `oauth_google.DEFAULT_SCOPES`).
No send/label-modify/delete commands in v1 - see "Deferred" at the end.

## Constraints inherited from owa-tools (do not relitigate)

Read `AGENTS.md` and `docs/architecture.md` in full before touching code.
The load-bearing rules for this tool specifically:

- **Stdlib only at runtime.** No `requests`, no Google API client library.
  Gmail's REST API is plain JSON-over-HTTPS with a bearer token - nothing
  about it needs a client library, `urllib` is enough (`owa_mail`/`owa_drive`
  already prove this pattern for Graph).
- **One shared HTTP path.** `no urllib.request.urlopen outside owa_core.http`
  is an enforced architecture-contract test
  (`src/tests/test_architecture_contracts.py`). `owa_gmail/api.py` must call
  `owa_core.http.request()` for every HTTP call, never `urlopen` directly.
- **One shared auth path.** `no subprocess.run(["owa-piggy", ...]) outside
  owa_core.auth` is also enforced. `owa_gmail/auth.py` must be a thin wrapper
  over `owa_core.auth.get_token_for_config()`, exactly like every existing
  tool's `auth.py`.
- **No owa-piggy internals.** Never import `owa_piggy`, never read
  `~/.config/owa-piggy` directly.
- **Every command has a schema entry; every mutating command declares
  confirmation/idempotency.** N/A for mutation in v1 since there are none, but
  the schema-per-command rule still applies to every read command.

## Auth

### Why `AUDIENCE = 'gmail'` is the right value, not an arbitrary one

owa-piggy's `resolve_audience()` (owa-piggy repo, `owa_piggy/scopes.py`) only
knows a fixed set of Entra resource names (`graph`, `outlook`, `teams`, ...).
`gmail` is not one of them and never will be - it's not an Entra resource URL.
For a `google`-provider profile, owa-piggy's `token_flow.exchange_fresh()`
ignores the audience/scope argument entirely (Google's OAuth scope is fixed
at consent time, not chosen per-request). So passing `--audience gmail` to
owa-piggy has exactly two possible outcomes:

- **Target profile is `OWA_PROVIDER=google`**: audience is ignored, token
  mints normally. Correct.
- **Target profile is MSAL** (the default/every other profile today):
  `resolve_audience()` errors with `unknown audience 'gmail'`, and
  `owa_core.auth.get_token` surfaces that as `AuthExpiredError`. The command
  fails loudly instead of silently minting a valid-but-wrong Graph token.

This fail-closed behavior only works because `gmail` is *not* a real
owa-piggy audience name. Do not add `gmail` to owa-piggy's `KNOWN_AUDIENCES`
- that would make this exact safety property go away (an MSAL profile would
then successfully mint some Entra-resource token under the `gmail` audience,
which is nonsense, but wouldn't error).

Live-verified precedent for this exact pattern: `owa-ado`'s `auth.py`
(`src/owa_ado/auth.py`) uses `AUDIENCE = 'devops'`, a real owa-piggy audience
name, but the same file's docstring explains the profile must be seeded
against a specific non-FOCI client. Same idea, one level more defensive here
because `gmail` has no owa-piggy meaning at all.

### `owa_gmail/auth.py`

Mirrors `src/owa_mail/auth.py` / `src/owa_drive/auth.py` exactly - this file
should be nearly a copy-paste with three constants changed:

```python
"""Token acquisition. Audience: gmail (a google-provider owa-piggy profile;
see gmail-cli.md "Auth" for why this string is deliberately not a real
owa-piggy audience name).
"""
from owa_core import auth as _core
from owa_core.errors import OwaError, emit_error

TOOL_NAME = 'owa-gmail'
AUDIENCE = 'gmail'
API_BASE = 'https://gmail.googleapis.com/gmail/v1/users/me'

def _log_token_remaining(access, debug):
    _core.log_token_remaining(access, debug)

def _refresh_via_owa_piggy(config, debug=False):
    try:
        token = _core.get_token_for_config(
            config, tool_name=TOOL_NAME, audience=AUDIENCE, debug=debug,
        )
    except OwaError as error:
        emit_error(error)
        return None
    return token.access_token

def do_token_refresh(config, debug=False):
    return _refresh_via_owa_piggy(config, debug=debug)

def setup_auth(config, debug=False):
    token = _core.get_token_for_config(
        config, tool_name=TOOL_NAME, audience=AUDIENCE, debug=debug,
    )
    return token.access_token, API_BASE
```

`API_BASE` is `.../users/me` (not just the API root) because every Gmail v1
endpoint is scoped under a user - using `me` as the special "authenticated
user" alias means the tool never needs to know the account's email address.

### Profile targeting - `--profile all` does NOT filter correctly for this tool

`owa_core.modes.run_with_output_modes()` supports `--profile all` fan-out via
`command_scopes` + `_filter_profiles_by_scope()`, which decides whether a
profile can run a command by decoding its access token as a JWT and checking
the `scp`/`roles` claim (`owa_core.jwt.scopes_in_token`).

**Google's access tokens are opaque bearer strings (`ya29....`), not JWTs.**
`scopes_in_token()` will throw internally (no reliable `.` split, or a
non-JSON payload) and its `except Exception: return set()` fallback kicks in
- an empty set never intersects any `acceptable` scope set, so a Google
profile would be silently *excluded* from its own tool's `--profile all`
fan-out. That's exactly backwards.

**Decision for v1: do not pass `command_scopes` to `run_with_output_modes()`
for this tool.** Pass `audience=auth_mod.AUDIENCE` (harmless, only used
alongside `command_scopes`) but leave `command_scopes` as the default
(`None`). Consequence: `owa-gmail messages --profile all` will include every
registered owa-piggy profile (MSAL ones too), and each MSAL profile's
per-profile run will fail with `AuthExpiredError` (owa-piggy's "unknown
audience" error, per the auth section above) and show up as a `"ok": false`
entry in the merged results - not silently dropped, not silently wrong, just
one noisy-but-harmless failed entry per non-Google profile.

Document this plainly in `docs/gmail.md` and tell users to either pin the
profile (`owa-gmail config --profile brkh-g`) or always pass an explicit
`--profile <alias>` rather than relying on `--profile all` / `-A`.

**Do not build a provider-aware fan-out filter to fix this now.** It would
require (a) owa-piggy's `profiles --json` to expose `OWA_PROVIDER` per row
(it currently doesn't - confirmed by reading `owa_piggy/cli.py`'s
`_do_profiles_list`), and (b) a new filtering mode in `owa_core.modes`
alongside the existing JWT-scope one. That's real design work justified by a
second Google-provider profile actually needing scoped fan-out, which does
not exist yet. Note it as a deferred owa_core enhancement, not a gmail-cli
workaround.

## Gmail API v1 surface this tool uses

Base: `https://gmail.googleapis.com/gmail/v1/users/me`. All endpoints
require `Authorization: Bearer <token>`; no API key needed (unlike some
Google API client-library examples that also pass a key - that's for
unauthenticated public-data APIs, doesn't apply here).

| Endpoint | Used by |
|---|---|
| `GET /messages` | `messages` (list) |
| `GET /messages/{id}?format=full` | `show` |
| `GET /messages/{id}?format=raw` | `get` |
| `GET /messages/{id}/attachments/{attachmentId}` | `attachments` |
| `GET /labels` | `labels` |
| `GET /profile` | `refresh` |

Pagination shape is **not** Graph's `@odata.nextLink`/`value` - it's
`{"messages": [{"id","threadId"}, ...], "nextPageToken": "...",
"resultSizeEstimate": N}`. `owa_core.http.paginate()` assumes the Graph shape
and cannot be reused as-is; `owa_gmail/api.py` needs its own small
`paginate_all()` built on top of `owa_core.http.request()` (not `urlopen`
directly - see "Constraints" above).

`owa_core.query.build_query()` (`src/owa_core/query.py`) has no OData-specific
behavior despite living next to OData-flavored callers - it's just
`f'{k}={quote(v)}'` joined by `&`. Safe to reuse verbatim for Gmail's flat
query params (`q`, `pageToken`, `maxResults`).

### `owa_gmail/api.py`

```python
"""Gmail API v1 HTTP helper. Base is per-user (.../users/me), so every
endpoint here is already scoped - callers never see the account address.
"""
from owa_core import http
from owa_core import query as query_mod
from . import auth as auth_mod


def _url(endpoint, params=None):
    url = f'{auth_mod.API_BASE}/{endpoint.lstrip("/")}'
    if params:
        url += '?' + query_mod.build_query(params)
    return url


def api_request(method, endpoint, access_token, params=None, body=None, debug=False):
    return http.request(
        method, _url(endpoint, params), token=access_token, body=body, debug=debug,
    ).json


def paginate_all(endpoint, access_token, params, list_key, *, max_pages=None, debug=False):
    """Follow Gmail's nextPageToken (NOT Graph's @odata.nextLink - see
    gmail-cli.md). Collects every `list_key` ('messages' or 'labels') item
    across all pages into one list."""
    items = []
    page_params = dict(params or {})
    pages = 0
    while True:
        payload = api_request('GET', endpoint, access_token, params=page_params, debug=debug)
        items.extend((payload or {}).get(list_key) or [])
        token = (payload or {}).get('nextPageToken')
        pages += 1
        if not token or (max_pages is not None and pages >= max_pages):
            break
        page_params = dict(page_params, pageToken=token)
    return items


def api_get_binary(endpoint, access_token, params=None, debug=False):
    """GET that returns raw bytes - used for format=raw messages and
    attachment downloads (both are base64url in the JSON body, NOT raw
    bytes over the wire - see messages.py's b64url_decode; this helper is
    for the rare case a caller wants the still-JSON-wrapped response's raw
    bytes, kept for symmetry with owa_drive.api but likely unused in v1
    since Gmail never streams raw binary at the HTTP layer the way Graph's
    /content endpoint does)."""
    return http.request(
        'GET', _url(endpoint, params), token=access_token, raw=True, debug=debug,
    ).bytes
```

Note the callout in `api_get_binary`'s docstring: unlike OneDrive's
`/content` endpoint (which streams raw bytes directly), Gmail never returns
raw bytes over HTTP - `format=raw` and attachment downloads both return JSON
with a base64url-encoded `data`/`raw` field. The actual byte-decoding
happens in `messages.py`, not `api.py`. Confirm this is actually true against
a live message during implementation (it should be, per Gmail API docs) and
drop `api_get_binary` from `api.py` entirely if it turns out to have no
caller - don't ship dead code.

### Known owa_core.http friction: Google's 403-shaped rate limiting

`owa_core.http._raise_for_http_error()` maps HTTP 403 unconditionally to
`ScopeInsufficientError`. Google's Gmail API sometimes returns a **403**
(not 429) for quota/rate-limit errors, with the real reason inside the JSON
body (`error.errors[].reason` = `rateLimitExceeded` / `userRateLimitExceeded`
/ `quotaExceeded`) - a shape `owa_core.http` doesn't parse (by design; it's
meant to stay body-shape-agnostic across all owa-tools consumers). Real 429s
(which do happen) are handled correctly by the existing retry logic.

**Do not build a Gmail-specific body-sniffing HTTP path to fix this.** That
duplicates HTTP status mapping, which `docs/architecture.md` explicitly says
to avoid. Ship v1 accepting the imperfection (a 403-shaped rate limit surfaces
as "access denied" rather than "retry me" - wrong error class, but not a
crash, and not silent). If this is actually hit in practice, the fix belongs
in `owa_core.http` (e.g. attaching the parsed body to `OwaError.cause` so a
caller *could* re-inspect it) as a shared enhancement, not a per-tool patch.

## Message shape and normalization

Gmail's message resource (`format=full`) has headers as a flat list
(`payload.headers: [{"name": "From", "value": "..."}]`, case-sensitive on
the wire but conventionally canonical-cased) and body content buried in a
recursive `payload.parts` tree (multipart messages can nest
`multipart/alternative` inside `multipart/mixed`, etc.) - nothing like
Outlook REST's flat `Body`/`BodyPreview` fields. `internalDate` is
epoch-milliseconds *as a string*.

Attachment bytes are **never** inlined in `format=full` - parts with a
`filename` carry only `body.attachmentId` and `body.size`; the actual bytes
need a separate `GET /messages/{id}/attachments/{attachmentId}` call.

### `owa_gmail/messages.py`

Pure functions, no I/O - mirrors `owa_mail/messages.py`'s "pure function,
tested exactly" style, but the shape being normalized is Gmail's, not
Outlook's; there is no meaningful code to port, only the pattern.

```python
"""Message JSON shaping for Gmail's payload/parts tree.

Gmail returns headers as a flat name/value list and body content as a
recursive multipart tree with base64url-encoded leaves - nothing like
Outlook REST's flat fields. These are pure functions; no I/O.
"""
import base64


def b64url_decode(data):
    """Gmail's body/attachment `data` is base64url per RFC 4648 S5,
    frequently WITHOUT padding. Same pad-fix as owa_piggy.jwt/owa_core.jwt
    use for JWT segments."""
    if not data:
        return b''
    pad = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def header(headers, name):
    """Case-insensitive lookup in Gmail's [{"name","value"}] header list."""
    target = name.lower()
    for h in headers or []:
        if (h.get('name') or '').lower() == target:
            return h.get('value') or ''
    return ''


def walk_parts(payload):
    """Yield every leaf part (no nested `parts`) in a message's payload
    tree, depth-first. A non-multipart message IS its own single leaf."""
    parts = payload.get('parts')
    if not parts:
        yield payload
        return
    for p in parts:
        yield from walk_parts(p)


def extract_bodies(payload):
    """Return (plain_text, html) - the first text/plain and text/html
    leaf part bodies found, decoded. Either may be '' if absent."""
    plain, html = '', ''
    for part in walk_parts(payload):
        mime = part.get('mimeType') or ''
        data = (part.get('body') or {}).get('data')
        if not data:
            continue
        if mime == 'text/plain' and not plain:
            plain = b64url_decode(data).decode('utf-8', errors='replace')
        elif mime == 'text/html' and not html:
            html = b64url_decode(data).decode('utf-8', errors='replace')
    return plain, html


def extract_attachments(payload):
    """Return [{filename, mimeType, attachmentId, size}] - metadata only,
    no bytes. A leaf part is an attachment iff it names a filename AND
    its body carries an attachmentId (inline images without a filename,
    or bodies with inline `data`, are not)."""
    out = []
    for part in walk_parts(payload):
        filename = part.get('filename') or ''
        body = part.get('body') or {}
        if filename and body.get('attachmentId'):
            out.append({
                'filename': filename,
                'mimeType': part.get('mimeType') or '',
                'attachmentId': body['attachmentId'],
                'size': body.get('size'),
            })
    return out


def normalize_message(raw, *, with_body=False):
    """Flatten a Gmail message resource to a stable snake_case shape.
    `with_body` controls whether bodies/attachments are extracted (the
    listing path skips this - see build_list_query's docstring for why
    Gmail can't embed bodies in a list response the way Graph can)."""
    payload = raw.get('payload') or {}
    headers = payload.get('headers') or []
    out = {
        'id': raw.get('id') or '',
        'thread_id': raw.get('threadId') or '',
        'label_ids': raw.get('labelIds') or [],
        'snippet': raw.get('snippet') or '',
        'internal_date_ms': int(raw.get('internalDate') or 0),
        'subject': header(headers, 'Subject'),
        'from': header(headers, 'From'),
        'to': header(headers, 'To'),
        'cc': header(headers, 'Cc'),
        'date': header(headers, 'Date'),
        'message_id': header(headers, 'Message-ID'),
    }
    if with_body:
        plain, html = extract_bodies(payload)
        out['body_plain'] = plain
        out['body_html'] = html
        out['attachments'] = extract_attachments(payload)
    return out


def build_list_query(sender='', to='', subject_q='', label='', unread=False,
                     has_attachment=False, since='', until='', search='',
                     max_results=25, page_token=''):
    """Build Gmail's flat query-param dict for a messages.list call.

    Gmail's `q` param is a single free-text search-operator string
    (from:/to:/subject:/label:/is:unread/has:attachment/after:/before:),
    space-joined terms are AND'd. Unlike Outlook REST there's no separate
    $filter/$select split - one string does all server-side filtering.
    `search` is a raw passthrough escape hatch (mirrors owa_mail's
    build_list_query `search` param) that REPLACES the built query
    entirely when given, matching the "power user wins" precedent there.
    """
    if search:
        q = search
    else:
        clauses = []
        if sender:
            clauses.append(f'from:{sender}')
        if to:
            clauses.append(f'to:{to}')
        if subject_q:
            clauses.append(f'subject:"{subject_q}"')
        if label:
            clauses.append(f'label:{label}')
        if unread:
            clauses.append('is:unread')
        if has_attachment:
            clauses.append('has:attachment')
        if since:
            clauses.append(f'after:{since.replace("-", "/")}')
        if until:
            clauses.append(f'before:{until.replace("-", "/")}')
        q = ' '.join(clauses)
    params = {'maxResults': max_results}
    if q:
        params['q'] = q
    if page_token:
        params['pageToken'] = page_token
    return params
```

`since`/`until` accept `YYYY-MM-DD` (matching the rest of the suite's date
convention, e.g. `owa_mail`) and get translated to Gmail's `YYYY/MM/DD`
`after:`/`before:` operators.

**Why listing can't embed bodies (the `--with-body` cost)**: Outlook REST's
`$select` lets `owa-mail messages --with-body` fetch full bodies in the same
paginated listing call (see `owa_mail/messages.py`'s
`LIST_SELECT_WITH_BODY`). Gmail's `messages.list` only ever returns
`{id, threadId}` - there is no `format`/`fields` param on the list endpoint
that embeds body content. A `--with-body` flag on `owa-gmail messages`
necessarily means: list ids (1 call, N/pageSize round trips), then one
`GET .../messages/{id}?format=full` **per message**. Document this cost
plainly in `docs/gmail.md` and in the flag's help text - it is not a bug to
fix, it's an actual API constraint. (Gmail does support a batch HTTP endpoint
that could collapse the N GETs into fewer multipart HTTP requests - see
"Deferred".)

## Command surface (v1, read-only)

Following `owa_drive/cli.py`'s exact structure: pure per-command arg-parsing
functions, `owa_core.schema` command specs, `owa_core.modes.run_with_output_modes`
as the `main()` entry point.

| Command | Verb shape | Notes |
|---|---|---|
| `messages` | list | Flags: `--from`, `--to`, `--subject`, `--label`, `--unread`, `--has-attachment`, `--since`, `--until`, `--search` (raw q passthrough), `--max-results` (default 25), `--page-token`, `--all` (follow pagination), `--with-body` (see cost note above), `--pretty` |
| `show <id>` | get | Full normalized message (headers + bodies + attachment metadata, no attachment bytes). `--pretty` for human view. |
| `get <id>` | get, binary stdout | `format=raw` - exact original RFC822 bytes (base64url-decoded), for `.eml`-equivalent extraction. `--out <file>` or stdout, like `owa-drive get`. |
| `attachments <message-id> <attachment-id>` | get, binary stdout | Downloads one attachment's decoded bytes. `--out <file>` or stdout. |
| `labels` | list | `{id, name, type}` rows. `--pretty` for a table. |
| `refresh` | local | `GET /profile`, prints `emailAddress` on success (mirrors `owa-drive refresh`'s `me` call pattern). |
| `config` | local | `--profile <alias>` pins `owa_piggy_profile`, matching every other tool's `config` subcommand. |
| `help` | local | Standard help text + `schema_mod.MULTI_PROFILE_HELP` + `schema_mod.MACHINE_SURFACE_HELP` blocks, exactly like `owa-drive`'s `print_help()`. |

`COMMAND_SCOPES` is intentionally **not** defined/wired (see "Profile
targeting" above).

`binary_stdout_commands=('get', 'attachments')` in the `main()` call to
`run_with_output_modes`, matching `owa_drive`'s `('get',)` pattern.

### `owa_gmail/cli.py` skeleton

```python
"""Argument parsing and dispatch for `owa-gmail`."""
import json
import sys

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core.errors import UsageError, _require_value, emit_message

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from .format import format_message_pretty, format_messages_pretty, format_labels_pretty
from .messages import build_list_query, normalize_message

# ... print_help(), cmd_messages, cmd_show, cmd_get, cmd_attachments,
# cmd_labels, cmd_refresh, cmd_config - each following owa_drive/cli.py's
# per-command "while args: flag, args = args[0], args[1:]" parsing style.

# ... COMMAND_SCHEMA list built from schema_mod.command()/schema_mod.flag(),
# one entry per row in the table above.

def _main(argv):
    ...  # identical control flow to owa_drive.cli._main: maybe_emit_schema,
         # help/version short-circuits, --debug/--profile stripping,
         # alias resolution, maybe_emit_subcommand_help,
         # precheck_required_args, then dispatch.

def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-gmail',
        sys.argv[1:] if argv is None else argv,
        _main,
        binary_stdout_commands=('get', 'attachments'),
        audience=auth_mod.AUDIENCE,
        # command_scopes intentionally omitted - see "Profile targeting"
    )
```

## Config

`owa_gmail/config.py` - identical shape to `owa_mail/config.py`, path
`~/.config/owa-gmail/config`, `ALLOWED_KEYS = ('owa_piggy_profile', 'debug')`.
No Gmail-specific persistent preferences needed for v1 (no default
`--max-results` override, no timezone - defer until a real need appears).

## Files to create

```
src/owa_gmail/
  AGENTS.md
  __init__.py           # from owa_core.version import suite_version; from .cli import main
  __main__.py            # sys.exit(main())
  auth.py
  api.py
  messages.py
  format.py              # format_message_pretty, format_messages_pretty, format_labels_pretty
  cli.py
docs/
  gmail.md
src/tests/gmail/
  __init__.py
  conftest.py             # fakes owa-piggy at the subprocess boundary, per docs/testing.md layer 4
  test_auth.py            # mirrors src/tests/todo/test_auth.py exactly
  test_api.py             # paginate_all with a fake urlopen; nextPageToken following
  test_messages.py        # b64url_decode padding cases, walk_parts on nested multipart,
                           # extract_bodies/extract_attachments, build_list_query for every flag combo
  test_format.py
  test_cli_commands.py    # one test per command, happy path + one failure path each
  test_cli_validation.py  # unknown command/flag exit 2, missing required value exits 2
  test_config.py
```

## Registration checklist (per `docs/new-tool-onboarding.md`)

- [ ] `pyproject.toml`: `owa-gmail = "owa_gmail:main"` in `[project.scripts]`
- [ ] `pyproject.toml`: `"owa_gmail"` in `[tool.setuptools] packages`
- [ ] `pyproject.toml`: `"owa_gmail"` in `[tool.coverage.run] source`
- [ ] `src/owa_core/registry.py`: append `"owa-gmail"` to `CONSUMER_TOOLS`
  (this alone also registers it with `owa` (`owa/cli.py`) and `owa-doctor`
  (`owa_doctor/probe.py`) - both derive from this tuple, confirmed by reading
  both files)
- [ ] `src/tests/test_architecture_contracts.py`: append `'owa_gmail'` to the
  `RUNTIME_DIRS` list. **This is the most important item on this checklist,
  not a paperwork step** - it's the actual test that enforces "no urlopen
  outside owa_core.http", "no owa-piggy subprocess outside owa_core.auth",
  and the mutating-command-declares-confirmation rule that this whole plan
  leans on as load-bearing constraints (see "Constraints inherited from
  owa-tools" above). Skipping this means `owa_gmail`'s code is silently
  exempt from every architecture guardrail in that file. Confirmed done
  correctly for `owa_ado` when it was added (its own diff added `'owa_ado'`
  here) - follow that precedent.
- [ ] `src/scripts/check_stdlib_only.py`: add `"owa_gmail"` to `LOCAL_PACKAGES`.
  **Caveat found by checking the current repo state**: `owa_ado`,
  `owa_planner`, `owa_sites`, `owa_teams`, and `owa_vids` are all *already
  missing* from this set today, meaning their runtime code isn't actually
  scanned by this checker at all (it both allowlists AND discovers files to
  scan from this same set) - an existing, unenforced gap, not something CI
  currently catches. Do this correctly for the new tools anyway rather than
  extending the gap; don't treat "it wasn't done for owa_ado" as license to
  skip it here.
- [ ] `src/scripts/check_docs_sync.py`: add a `'owa-gmail': ('docs/gmail.md',
  GMAIL_SCHEMA)` entry to the `DOCS` map (needs a `GMAIL_SCHEMA` import at the
  top of that script, mirroring the existing per-tool schema imports)
- [ ] `src/tests/contract/test_suite_contract.py`: add `"owa_gmail"` to the
  module-level `TOOLS` tuple. Confirmed by reading the file: `TOOLS` is its
  own hardcoded tuple there, **not** derived from
  `owa_core.registry.CONSUMER_TOOLS` - registering in the registry alone
  does not add this tool to the cross-tool contract tests
  (`test_all_tools_expose_help_and_version`, `test_destructive_commands_declare_confirmation_metadata`,
  etc.). **Also currently missing** for `owa_ado`/`owa_planner`/`owa_sites`/
  `owa_teams`/`owa_vids` - same unenforced-gap caveat as the
  `check_stdlib_only.py` item above. Do it correctly here regardless.
- [ ] `README.md`: one-line tool-table entry linking to `docs/gmail.md`
- [ ] `CHANGELOG.md`: **not per-commit** - confirmed by reading the file,
  this repo's changelog is organized by `## vX.Y.Z` release sections added
  at tag time (see `AGENTS.md` "Cutting a release"), not a rolling
  "Unreleased" header. Note `owa-gmail` under the next release section when
  that release is actually cut; don't add a section for it now.
- [ ] Root `AGENTS.md`: index-table entry pointing at
  `src/owa_gmail/AGENTS.md`
- [ ] `src/owa_gmail/AGENTS.md`: local invariants (mirrors `owa_drive/AGENTS.md`'s
  shape - see below)
- [ ] `docs/gmail.md`: purpose, install assumption, auth audience/scope
  caveats (readonly only, `--with-body` cost, `--profile all` caveat), every
  command with an example, output shapes, error modes, retry/idempotency
  notes, security notes

### `src/owa_gmail/AGENTS.md` draft

```markdown
# AGENTS.md

`owa_gmail` is a read-only Gmail CLI for a google-provider owa-piggy profile.

- Auth audience is `gmail` - deliberately not a real owa-piggy audience name.
  See gmail-cli.md "Auth" before changing this.
- Read-only in v1 (`gmail.readonly` scope only) - no send/modify/delete
  commands. See gmail-cli.md "Deferred" before adding any.
- `--profile all` does not scope-filter correctly for Google tokens (they're
  opaque, not JWTs) - do not wire `command_scopes` without re-reading
  gmail-cli.md "Profile targeting" first.
- Binary stdout (`get`, `attachments`) must stay exact bytes; base64url
  decoding happens once, in `messages.py`.
- Docs live in `docs/gmail.md`; update before release.

Nearest tests: `src/tests/gmail/`.

Verify:

```bash
.venv/bin/ruff check src/owa_gmail src/tests/gmail
.venv/bin/python -m pytest -q src/tests/gmail
```
```

## Testing plan (per `docs/testing.md`)

Minimum set from `docs/new-tool-onboarding.md`, mapped to files:

- Import smoke, `--help`, `--help --json`, `--version`, `schema` → covered by
  `src/tests/contract/test_suite_contract.py` **once `owa_gmail` is added to
  that file's `TOOLS` tuple** (a separate, manual step from the registry
  addition - see the registration checklist above; do not assume registry
  membership alone triggers these tests)
- Unknown command/flag exits 2, missing required flag value exits 2 →
  `test_cli_validation.py`
- Auth-broker fake happy/failure path → `test_auth.py`, fixtures identical
  in shape to `src/tests/todo/test_auth.py` (`FakeProc`, `_patch_owa_piggy`)
- One success command emits JSON on stdout with empty stderr; one `--pretty`
  command emits human output → `test_cli_commands.py`
- All query/path/payload builders (`build_list_query` for every flag) → `test_messages.py`
- All normalizers (`normalize_message`, `extract_bodies`,
  `extract_attachments`, `walk_parts`, `b64url_decode` including the
  no-padding case) → `test_messages.py`
- The no-secret scanner (`check_no_secrets.py`) and stdlib-only checker
  (`check_stdlib_only.py`) both walk `src/` automatically once the package
  exists and is registered - no test-writing needed, just confirm both
  scripts pass after implementation
- **Google-specific case not in the generic checklist**: a `test_messages.py`
  case for a multipart message with nested `multipart/alternative` inside
  `multipart/mixed` (the common real-world Gmail shape - plain text +
  html + one attachment) to prove `walk_parts` actually recurses correctly,
  not just handles a flat one-level `parts` list.

Live test (`src/tests/gmail/test_live.py`, gated on `OWA_LIVE_TESTS=1` +
`OWA_PROFILE=brkh-g`): `owa-gmail messages --max-results 1`,
`owa-gmail labels`, `owa-gmail refresh` - read-only smoke against the real
account, matching the existing `<tool>/test_live.py` pattern.

## Deferred (explicitly out of scope for v1)

- **Write commands** (send, modify labels, delete, trash) - need
  `gmail.send`/`gmail.modify` scopes, which means updating owa-piggy's
  Google OAuth consent screen and getting the `brkh-g` profile to
  re-consent. Not needed for the motivating YAAMS-ingestion use case.
- **Threads** (`threads`/`threads show`) - Gmail's thread resource is mostly
  "a list of messages"; useful but not required for v1's flat-message
  ingestion use case. Straightforward to add later following the same
  pattern as `messages`/`show`.
- **Batch HTTP requests** to collapse `--with-body`'s N sequential GETs into
  fewer multipart HTTP round trips (Gmail supports a
  `https://www.googleapis.com/batch/gmail/v1` endpoint). Real perf win for
  large mailboxes, but multipart/mixed request+response construction and
  parsing over stdlib `urllib` is nontrivial and not justified until
  sequential fetching is actually proven too slow for a real ingestion
  workload.
- **`labelIds`-param filtering** instead of the `label:` search operator (see
  `build_list_query`) - would need a `labels.list` round trip to resolve a
  user label's display name to its opaque id first. The `label:` operator
  in `q` already does this server-side; only worth the extra round trip if
  ever proven faster or more precise in practice.
- **Provider-aware `--profile all` fan-out filtering** - see "Profile
  targeting" above. Needs an owa-piggy change (expose `OWA_PROVIDER` in
  `profiles --json`) plus an `owa_core.modes` change; deferred until a
  second Google-provider profile actually needs it.
