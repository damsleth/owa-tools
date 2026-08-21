# Plan: `owa-gdrive` (Google Drive read CLI)

Status: planning only, nothing implemented yet.

## Context

Same motivation and same auth foundation as `gmail-cli.md` - read that plan
first, especially its "Auth" and "Profile targeting" sections, since almost
everything there applies here unchanged (opaque Google tokens, the
deliberately-not-a-real-owa-piggy-audience trick, the `--profile all`
caveat). This document only covers what's actually different: Drive's API
shape, its query language, and the Google-native-file export problem, which
has no equivalent anywhere else in this suite.

**Naming**: binary `owa-gdrive`, package `owa_gdrive`, audience string
`gdrive`. Deliberately **not** `drive` - `owa-drive` already exists in this
suite and means OneDrive/Graph; reusing `drive` as the Google audience name
would be a constant source of "which drive" confusion in code, docs, and
anyone's shell history. `gdrive` is also unclaimed in owa-piggy's
`KNOWN_AUDIENCES` (confirmed by reading `owa_piggy/scopes.py`), which is the
same property that makes `gmail` safe to use as an audience string for the
sibling tool - see `gmail-cli.md`'s "Auth" section for exactly why an
unclaimed name is a *feature*, not a placeholder.

**Scope for v1**: read-only, matching the `drive.readonly` scope actually
consented on the Google OAuth client. No `put`/`rm`/move/rename - see
"Deferred".

## Constraints inherited from owa-tools

Identical to `gmail-cli.md`'s "Constraints" section - stdlib only, one
shared HTTP path (`owa_core.http`, never raw `urlopen`), one shared auth path
(`owa_core.auth`, never raw `owa-piggy` subprocess calls outside it), no
`owa_piggy` imports, every command has a schema entry. Not repeating the
citations here; go read that section.

One addition specific to this tool: `docs/architecture.md`'s "every mutating
command declares confirmation/idempotency metadata" rule is **inactive** for
v1 (no mutating commands exist), but do not forget it the moment `put`/`rm`
are added in a future version - `owa_drive/cli.py`'s `rm`/`put` schema
entries (`mutates=True`, `destructive=True`, `confirmation=True` for `rm`)
are the template to copy at that point.

## Auth

`owa_gdrive/auth.py` is byte-for-byte the same shape as `owa_gmail/auth.py`,
three constants changed:

```python
"""Token acquisition. Audience: gdrive (a google-provider owa-piggy
profile; see gmail-cli.md "Auth" for why this string is deliberately not
a real owa-piggy audience name - same reasoning applies here).
"""
from owa_core import auth as _core
from owa_core.errors import OwaError, emit_error

TOOL_NAME = 'owa-gdrive'
AUDIENCE = 'gdrive'
API_BASE = 'https://www.googleapis.com/drive/v3'

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

Unlike Gmail's `.../users/me` base, Drive API v3's base has no per-user
prefix - the authenticated user's own Drive is implicit from the token, and
every endpoint (`/files`, `/files/{id}`, `/about`) is already scoped by it.

### Profile targeting - same caveat as gmail-cli, do not re-derive it

Do not pass `command_scopes` to `run_with_output_modes()` for the same
reason as `owa-gmail`: Google's opaque access tokens break
`owa_core.jwt.scopes_in_token()`'s JWT decode, which would silently *exclude*
the one profile that should be included in a `--profile all` fan-out. Pass
`audience=auth_mod.AUDIENCE` only. Full explanation lives in
`gmail-cli.md`'s "Profile targeting" section - point there instead of
duplicating it in code comments across two packages.

## Drive API v3 surface this tool uses

Base: `https://www.googleapis.com/drive/v3`.

| Endpoint | Used by |
|---|---|
| `GET /files?q=...` | `ls` (also handles `--search`/`--query`) |
| `GET /files/{id}` | `show` |
| `GET /files/{id}?alt=media` | `get` (regular, non-Google-native files) |
| `GET /files/{id}/export?mimeType=...` | `get` (Google Docs/Sheets/Slides only) |
| `GET /about?fields=user` | `refresh` |

Pagination shape is the same `nextPageToken` pattern as Gmail
(`{"files": [...], "nextPageToken": "..."}`) but with list key `files`
instead of `messages`/`labels`. **Do not duplicate `paginate_all` between
`owa_gmail` and `owa_gdrive`** - both need it, but it's a two-Google-tool
pattern, not (yet) a suite-wide one. Two reasonable options, pick during
implementation based on which lands first:

1. If `owa_gmail` ships first, `owa_gdrive/api.py` can import and reuse its
   `paginate_all` (`from owa_gmail import api as gmail_api` is allowed - both
   are local suite packages) - but this creates a weird dependency direction
   (a Drive tool depending on a Gmail tool's internals for something that
   has nothing to do with either domain).
2. **Preferred**: lift the shared `nextPageToken`-following logic into
   `owa_core` as `owa_core.http.paginate_by_token(url, *, token, list_key,
   token_param='pageToken', token_field='nextPageToken', ...)` once both
   tools exist and the duplication is real (not hypothetical). This is
   exactly the kind of "duplicated HTTP status/pagination mapping"
   `docs/architecture.md` warns against - but doing it *before* a second
   caller exists would be speculative generalization from a single example.
   Ship both tools with their own copy first; refactor into `owa_core` in the
   same change that adds a third Google-flavored tool, or immediately after
   both `owa-gmail` and `owa-gdrive` ship if the duplication bothers whoever
   reviews it. Note this explicitly as a fast-follow, not a "later maybe".

### `owa_gdrive/api.py`

```python
"""Drive API v3 HTTP helper."""
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


def paginate_all(endpoint, access_token, params, *, max_pages=None, debug=False):
    """Follow Drive's nextPageToken. See gdrive-cli.md for why this is a
    near-duplicate of owa_gmail.api.paginate_all and the plan to
    deduplicate once a third Google-flavored tool exists."""
    items = []
    page_params = dict(params or {})
    pages = 0
    while True:
        payload = api_request('GET', endpoint, access_token, params=page_params, debug=debug)
        items.extend((payload or {}).get('files') or [])
        token = (payload or {}).get('nextPageToken')
        pages += 1
        if not token or (max_pages is not None and pages >= max_pages):
            break
        page_params = dict(page_params, pageToken=token)
    return items


def api_get_binary(endpoint, access_token, params=None, debug=False):
    """GET that returns raw bytes. Used for both alt=media (direct
    content) and /export (converted content) - unlike Gmail, Drive DOES
    stream real binary bytes over HTTP for these, not a base64-in-JSON
    envelope, so `raw=True` genuinely returns the final file bytes here."""
    return http.request(
        'GET', _url(endpoint, params), token=access_token, raw=True, debug=debug,
    ).bytes
```

Note the contrast with `owa_gmail/api.py`'s equivalent docstring: Drive's
binary endpoints are genuinely raw-bytes-over-HTTP (like OneDrive's
`/content`), unlike Gmail where everything is JSON-wrapped base64url. This
is the one place `owa_drive/api.py`'s `api_get_binary` (Graph OneDrive) is
actually the closer template, not `owa_gmail`'s.

## The Google-native-file export problem (this tool's hardest edge case)

Google Docs, Sheets, and Slides have **no binary content of their own** -
`alt=media` on a `application/vnd.google-apps.document` file returns
`403 fileNotDownloadable` (or similar), because there is no file, only a
live Google-hosted document. The only way to get bytes out of one is
`/files/{id}/export?mimeType=<target>`, and the target must be one of a
fixed, type-specific set Google documents at
https://developers.google.com/drive/api/guides/ref-export-formats (verify
this list is still current during implementation - Google has changed export
mimeType support before, e.g. dropping some legacy formats).

Everything else (PDF, plain files, images, uploaded Office docs saved
as-is, zip, etc.) has real binary content and uses `alt=media` directly - no
export step, no format choice.

### `owa_gdrive/files.py`

```python
"""File JSON shaping and the Google-native export-format decision."""

GOOGLE_NATIVE_PREFIX = 'application/vnd.google-apps.'

# One sensible default export target per Google-native type, chosen for
# text-extraction use cases (the motivating YAAMS-ingestion consumer wants
# readable text, not print-perfect PDFs). Override per-call with
# --export-mime. Verify against
# https://developers.google.com/drive/api/guides/ref-export-formats during
# implementation - this list can drift.
DEFAULT_EXPORT_MIME = {
    'application/vnd.google-apps.document': 'text/plain',
    'application/vnd.google-apps.spreadsheet': 'text/csv',
    'application/vnd.google-apps.presentation': 'text/plain',
}


def is_google_native(mime_type):
    return (mime_type or '').startswith(GOOGLE_NATIVE_PREFIX)


def resolve_export_mime(mime_type, override=None):
    """Return the export target mimeType for a Google-native file, or
    None if `mime_type` isn't Google-native (caller should use alt=media
    instead). Raises ValueError if native but no default/override exists
    (e.g. a Google-native type not in DEFAULT_EXPORT_MIME - Forms,
    Drawings, etc. - deliberately not covered in v1)."""
    if not is_google_native(mime_type):
        return None
    if override:
        return override
    if mime_type in DEFAULT_EXPORT_MIME:
        return DEFAULT_EXPORT_MIME[mime_type]
    raise ValueError(
        f'{mime_type!r} has no default export target; pass --export-mime explicitly'
    )


def normalize_file(entry):
    """Project a Drive `files` resource into a flat shape. Mirrors
    owa_drive/items.py's normalize_item in spirit (kind/size/modified/name
    shape), but Drive has no OneDrive-style parentPath - `parents` is a
    list of opaque folder ids (usually length 1; Shared Drives can have
    more historically, though modern My-Drive files have exactly one)."""
    is_folder = entry.get('mimeType') == f'{GOOGLE_NATIVE_PREFIX}folder'
    return {
        'id': entry.get('id') or '',
        'name': entry.get('name') or '',
        'kind': 'folder' if is_folder else 'file',
        'mime_type': entry.get('mimeType') or '',
        'is_google_native': is_google_native(entry.get('mimeType')),
        'size': entry.get('size'),  # Drive omits `size` for Google-native files entirely
        'modified': entry.get('modifiedTime') or '',
        'parents': entry.get('parents') or [],
        'web_view_link': entry.get('webViewLink') or '',
        'trashed': bool(entry.get('trashed')),
    }


def build_list_query(folder='', name='', search='', file_type='', raw_query=''):
    """Build Drive's `q` search-expression string.

    Drive's query language needs single-quoted string literals with
    internal single quotes escaped as \\' - NOT the same escaping as
    Outlook REST's OData `''`-doubling (see owa_mail/messages.py's
    `sender.replace("'", "''")` for contrast) or Gmail's bare-token
    operators. `raw_query` is a passthrough escape hatch, same
    "power user wins, replaces everything" precedent as owa_gmail's
    `search` param in build_list_query.
    """
    if raw_query:
        return raw_query
    clauses = ['trashed = false']  # default: never surface trash, matches
                                    # every other owa-tools listing's
                                    # implicit "active items only" behavior
    if folder:
        clauses.append(f"'{_escape(folder)}' in parents")
    if name:
        clauses.append(f"name contains '{_escape(name)}'")
    if search:
        clauses.append(f"fullText contains '{_escape(search)}'")
    if file_type == 'folder':
        clauses.append(f"mimeType = '{GOOGLE_NATIVE_PREFIX}folder'")
    elif file_type == 'file':
        clauses.append(f"mimeType != '{GOOGLE_NATIVE_PREFIX}folder'")
    return ' and '.join(clauses)


def _escape(value):
    return value.replace("'", "\\'")
```

`ls` with no `--folder` lists the Drive root - Drive's root folder id is the
literal reserved string `root`, so `--folder root` and omitting `--folder`
should behave identically (default `folder=''` in the CLI layer, and
`build_list_query` only adds the `in parents` clause when `folder` is
truthy - meaning "no folder filter" and "root filter" are actually
*different* queries: omitting `--folder` entirely lists everything
matching the other filters regardless of location, while `--folder root`
scopes to direct root children only). Get this distinction right in the
CLI layer's default: `ls` with zero flags should default to `--folder root`
(list root's children, matching `owa-drive ls`'s "default: drive root"
behavior), not "no folder filter at all" (which would return every file in
the whole Drive, an extremely surprising default for a bare `ls`).

## No path-based addressing in v1

OneDrive/Graph lets you address `/Documents/Q1 plan.docx` directly
(`owa_drive/paths.py` translates that to `root:/Documents/Q1 plan.docx:`).
**Drive has no native path concept** - a file's location is a `parents` id
list, and building a human path requires walking parent ids backward one
API call at a time (or forward, one `files.list` call per path segment).

Do not build a synthetic path resolver for v1. It would be N round trips for
an N-segment path, semi-broken for files with multiple parents or duplicate
names in the same folder (both legal in Drive, neither exist in OneDrive),
and not needed for the motivating ingestion use case, which can walk
`ls <folder-id>` → child ids → `ls <child-id>` naturally, or use `--search`/
`--query` to find a file by name/content directly. If ergonomic path
addressing is ever actually requested, it's a genuinely new feature (with
its own ambiguity-handling design), not a small addition - flag that
explicitly rather than half-building it now.

## Command surface (v1, read-only)

| Command | Verb shape | Notes |
|---|---|---|
| `ls` | list | Flags: `--folder <id>` (default: `root`), `--name <text>`, `--search <text>` (fullText), `--type file\|folder`, `--query <raw-q>` (passthrough, replaces all other filters), `--all` (follow pagination), `--pretty` |
| `show <id>` | get | Full normalized metadata. `--pretty` for human view (mirrors `owa_drive/format.py`'s `format_item_pretty` shape - kind/size/mimeType/modified/parent/url/id). |
| `get <id>` | get, binary stdout | `alt=media` for regular files; auto-`export` (with `DEFAULT_EXPORT_MIME`) for Google-native files, override via `--export-mime <type>`. `--out <file>` or stdout, like `owa-drive get`. Errors clearly (not a raw 403) when a Google-native file has no default export mime and none was given - see `resolve_export_mime`'s `ValueError`, which the CLI layer should catch and re-raise as a `UsageError` with an actionable message. |
| `refresh` | local | `GET /about?fields=user`, prints the authenticated user's display name on success. |
| `config` | local | `--profile <alias>` pins `owa_piggy_profile`. |
| `help` | local | Standard help + `MULTI_PROFILE_HELP` + `MACHINE_SURFACE_HELP`, like every other tool. |

`COMMAND_SCOPES` intentionally **not** defined (same reasoning as
`owa-gmail`). `binary_stdout_commands=('get',)`.

### `owa_gdrive/cli.py` skeleton

Same shape as `owa_drive/cli.py`'s `_main`/`main` control flow (schema
short-circuit, help/version, `--debug`/`--profile` stripping, alias
resolution, `precheck_required_args`, dispatch) minus `put`/`rm` and their
batch-upload machinery entirely - there's real less code here than
`owa_drive/cli.py`, not a full copy.

```python
"""Argument parsing and dispatch for `owa-gdrive`."""
import sys

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core.errors import UsageError, emit_message

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from .files import build_list_query, normalize_file, resolve_export_mime
from .format import format_file_pretty, format_files_pretty

# ... cmd_ls, cmd_show, cmd_get, cmd_refresh, cmd_config
# ... COMMAND_SCHEMA
# ... _main (mirrors owa_drive.cli._main, ls/show/get/refresh/config only)

def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-gdrive',
        sys.argv[1:] if argv is None else argv,
        _main,
        binary_stdout_commands=('get',),
        audience=auth_mod.AUDIENCE,
    )
```

## Config

`owa_gdrive/config.py` - same shape as `owa_drive/config.py`, path
`~/.config/owa-gdrive/config`, `ALLOWED_KEYS = ('owa_piggy_profile', 'debug')`.

## Files to create

```
src/owa_gdrive/
  AGENTS.md
  __init__.py
  __main__.py
  auth.py
  api.py
  files.py               # normalize_file, build_list_query, is_google_native,
                          # resolve_export_mime, DEFAULT_EXPORT_MIME
  format.py               # format_file_pretty, format_files_pretty
  cli.py
docs/
  gdrive.md
src/tests/gdrive/
  __init__.py
  conftest.py
  test_auth.py            # mirrors src/tests/todo/test_auth.py
  test_api.py             # paginate_all nextPageToken following
  test_files.py           # build_list_query for every flag combo (incl. the
                           # quote-escaping case), normalize_file for both
                           # regular and Google-native files, resolve_export_mime
                           # happy path + the "no default, no override" ValueError
  test_format.py
  test_cli_commands.py
  test_cli_validation.py
  test_config.py
```

## Registration checklist (per `docs/new-tool-onboarding.md`)

Identical shape to `gmail-cli.md`'s checklist, `gdrive`/`owa-gdrive`
substituted throughout:

- [ ] `pyproject.toml`: `owa-gdrive = "owa_gdrive:main"` in `[project.scripts]`
- [ ] `pyproject.toml`: `"owa_gdrive"` in `[tool.setuptools] packages`
- [ ] `pyproject.toml`: `"owa_gdrive"` in `[tool.coverage.run] source`
- [ ] `src/owa_core/registry.py`: append `"owa-gdrive"` to `CONSUMER_TOOLS`
  (registers with `owa` and `owa-doctor` automatically, same as gmail-cli.md notes)
- [ ] `src/tests/test_architecture_contracts.py`: append `'owa_gdrive'` to
  `RUNTIME_DIRS`. **Not a paperwork step** - this is the test that actually
  enforces "no urlopen outside owa_core.http" / "no owa-piggy subprocess
  outside owa_core.auth" / mutating-command-declares-confirmation. See
  `gmail-cli.md`'s identical checklist item for the full explanation
  (confirmed correctly done for `owa_ado` - follow that precedent).
- [ ] `src/scripts/check_stdlib_only.py`: add `"owa_gdrive"` to
  `LOCAL_PACKAGES`. Same caveat as `gmail-cli.md`: `owa_ado` and several
  other existing tools are demonstrably missing from this set today (an
  unenforced gap, confirmed by reading the current file) - do it correctly
  here anyway.
- [ ] `src/scripts/check_docs_sync.py`: add `'owa-gdrive': ('docs/gdrive.md',
  GDRIVE_SCHEMA)` to the `DOCS` map
- [ ] `src/tests/contract/test_suite_contract.py`: add `"owa_gdrive"` to the
  module-level `TOOLS` tuple - separate, manual step from the registry
  addition (confirmed: `TOOLS` there is its own hardcoded tuple, also
  currently missing several existing tools). See `gmail-cli.md`'s identical
  item; do not skip it.
- [ ] `README.md`: one-line tool-table entry linking to `docs/gdrive.md`
- [ ] `CHANGELOG.md`: **not per-commit** - this repo's changelog is
  organized by `## vX.Y.Z` release sections added at tag time (confirmed by
  reading the file and `AGENTS.md` "Cutting a release"). Note `owa-gdrive`
  when a release is actually cut, not now.
- [ ] Root `AGENTS.md`: index-table entry pointing at
  `src/owa_gdrive/AGENTS.md`
- [ ] `src/owa_gdrive/AGENTS.md`: local invariants (draft below)
- [ ] `docs/gdrive.md`: purpose, install assumption, auth audience/scope
  caveats (readonly only, no path addressing, export-mime behavior,
  `--profile all` caveat), every command with an example, output shapes,
  error modes, retry/idempotency notes, security notes

### `src/owa_gdrive/AGENTS.md` draft

```markdown
# AGENTS.md

`owa_gdrive` is a read-only Google Drive CLI for a google-provider
owa-piggy profile.

- Auth audience is `gdrive` - deliberately not `drive` (that's owa-drive's
  OneDrive audience) and not a real owa-piggy audience name. See
  gmail-cli.md "Auth" for why an unclaimed string is deliberate.
- Read-only in v1 (`drive.readonly` scope only) - no put/rm/move/rename.
  See gdrive-cli.md "Deferred" before adding any.
- No path-based addressing (Drive has no native path concept) - `ls
  <folder-id>` / `show <id>` / `get <id>` only. See gdrive-cli.md "No
  path-based addressing in v1" before building one.
- Google-native files (Docs/Sheets/Slides) have no binary content - `get`
  must route them through `/export?mimeType=...`, never `alt=media`. See
  `files.resolve_export_mime`.
- `--profile all` does not scope-filter correctly for Google tokens - same
  caveat as owa_gmail, see gmail-cli.md "Profile targeting".
- Binary stdout (`get`) must stay exact bytes.
- Docs live in `docs/gdrive.md`; update before release.

Nearest tests: `src/tests/gdrive/`.

Verify:

```bash
.venv/bin/ruff check src/owa_gdrive src/tests/gdrive
.venv/bin/python -m pytest -q src/tests/gdrive
```
```

## Testing plan

Same shape as `gmail-cli.md`'s testing plan; Drive-specific additions:

- `test_files.py`: `build_list_query`'s single-quote escaping
  (`_escape("O'Brien's notes")` → literal `\'` sequences, not OData-style
  doubled quotes - a real, easy-to-get-wrong difference from every other
  query builder in this suite)
- `test_files.py`: `resolve_export_mime` for all three `DEFAULT_EXPORT_MIME`
  entries, an `--export-mime` override, a non-native file (returns `None`,
  caller should use `alt=media`), and a native type with no default AND no
  override (raises `ValueError` - the CLI layer's corresponding
  `test_cli_commands.py` case should assert this surfaces as a `UsageError`
  with exit code 2, not an unhandled exception or a raw 403 passthrough)
- `test_api.py`: confirm `api_get_binary` returns real raw bytes (not a
  JSON-wrapped envelope) for both the `alt=media` and `/export` code paths,
  documenting the contrast with `owa_gmail`'s always-JSON-wrapped shape

Live test (`OWA_LIVE_TESTS=1`, `OWA_PROFILE=brkh-g`): `owa-gdrive ls`,
`owa-gdrive show <some-known-id>`, `owa-gdrive refresh`. Do not add a live
`get` test against a real Google Doc unless a stable, known-safe test
document id is set aside for it - a live test that exports arbitrary Drive
content is a bigger blast radius than reading metadata.

## Deferred (explicitly out of scope for v1)

- **Write commands** (`put`, `rm`, move, rename) - need at minimum
  `drive.file` scope (NOT the broader `drive` scope - `drive.file` only
  grants access to files the app itself created/opened, which is the
  correct, narrower choice for a future write feature; the full `drive`
  scope would grant blanket read/write over the user's entire Drive and
  should not be requested). Needs owa-piggy consent-screen scope changes
  and profile re-consent, same as gmail-cli.md's deferred write scopes.
- **Path-based addressing** - see the dedicated section above.
- **Shared-drive support** (`supportsAllDrives`, `driveId` params) - v1
  targets My Drive only; Shared Drives have different permission and
  parent-id semantics that add real complexity for a use case (personal
  BRKH ingestion) that doesn't currently need them.
- **`paginate_all` deduplication into `owa_core`** - see the dedicated note
  in "Drive API v3 surface" above; fast-follow once both Google tools exist,
  not a v1 blocker.
- **Provider-aware `--profile all` fan-out filtering** - same deferred item
  as `gmail-cli.md`, same reasoning, do not duplicate the design there.
