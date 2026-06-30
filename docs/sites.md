# owa-sites

SharePoint CLI for Microsoft 365. Browse sites, document libraries, list items,
and files, and run tenant search — over the **SharePoint REST API**.
Pipe-friendly JSON by default, `--pretty` for humans. **Read-only** in this
version.

```sh
brew install damsleth/tap/owa-tools
owa-sites site owa-casa --pretty
```

`owa-sites` is part of the `owa-tools` suite and shares the `owa-piggy` auth
broker. You can also reach it through the umbrella: `owa sites lists --site
owa-casa` is identical to `owa-sites lists --site owa-casa`.

---

## Auth and scope

owa-sites does **not** use the Microsoft Graph `/sites` API — the shared token
lacks `Sites.Read.All`, so Graph `/sites` returns `403` (that is the dead path
`owa-graph sites` rides). Instead it talks to the **SharePoint REST API** on the
per-tenant host `https://<tenant>.sharepoint.com/.../_api/...`.

That host's token is minted by overriding owa-piggy's scope to the SharePoint
resource:

```sh
owa-piggy token --scope 'https://<tenant>.sharepoint.com/.default'
```

which yields a token carrying `Sites.FullControl.All` + `Files.ReadWrite.All`.
owa-sites does this for you. The tenant host is **auto-discovered** from the
tenant's initial `*.onmicrosoft.com` domain (via `GET /organization`,
`Organization.Read.All`); pin it to skip discovery:

```sh
owa-sites config --host contoso.sharepoint.com
owa-sites --profile work site --pretty
```

> `Sites.FullControl.All` is full control (read + write). This version only
> issues reads; file upload and other writes are deferred.

---

## Site addressing

The `--site` value accepts a bare name, an explicit path, a full SharePoint
URL, or nothing for the tenant **root** site:

| `--site` value | Targets |
| --- | --- |
| `owa-casa` | `https://<host>/sites/owa-casa` |
| `sites/owa-casa` | same (explicit) |
| `teams/Marketing` | `https://<host>/teams/Marketing` |
| `https://<host>/sites/owa-casa` | a pasted URL — only its server-relative path is kept |
| *(omitted)* | the tenant root site |

A pasted site URL is resolved to its server-relative path; the `site` command's
JSON output carries the resolved web `id`, so a URL in yields its site id out.
Raw site GUIDs are **not** accepted: SharePoint REST is path-based and has no
host-relative "open web by id" (that is a Graph `/sites/{id}` operation, the dead
path owa-sites deliberately avoids), so address sites by name, path, or URL.

The `site` command also accepts the address as a bare positional
(`owa-sites site owa-casa`). Pin a default with `owa-sites config --site
owa-casa`.

---

## The output contract

**JSON on stdout, logs on stderr.** SharePoint's PascalCase wire shape is
normalized to stable lowercase keys, so the CLI composes with `jq`:

```sh
owa-sites lists --site owa-casa | jq '.[] | select(.itemCount > 0) | .title'
owa-sites search --q "budget" | jq '.[].Path'
```

A list normalizes to:

```json
[
  {
    "title": "Documents",
    "id": "list-guid-redacted",
    "itemCount": 5,
    "baseTemplate": 101,
    "hidden": false
  }
]
```

`lists` hides system/hidden lists by default; pass `--all-lists` to include
them. `lists` and `items` accept OData passthrough flags — `--filter`,
`--orderby`, and `--expand` — appended to the underlying query.

Collection reads follow SharePoint's `odata.nextLink`. `items` walks up to
`--max-pages` pages (default 50); if the cap trips while more pages remain it
prints a truncation warning to **stderr**. Pass `--all` to follow every page
without a cap.

---

## Commands

```sh
owa-sites site owa-casa --pretty               # a site web (title, url)
owa-sites site --site sites/owa-casa           # explicit path form

owa-sites lists --site owa-casa --pretty       # lists / document libraries
owa-sites lists --site owa-casa --all-lists    # include hidden/system lists

owa-sites items --site owa-casa --list Documents          # list items
owa-sites items --site owa-casa --list Documents --select Title,Modified --top 50
owa-sites items --site owa-casa --list Documents --filter "Id gt 0" --orderby "Modified desc" --all
owa-sites item --site owa-casa --list Documents 42        # one item by id

owa-sites files --site owa-casa --path "/sites/owa-casa/Shared Documents"
owa-sites file --site owa-casa <unique-id>                # one file by UniqueId

owa-sites search --q "quarterly report" --pretty          # tenant search
owa-sites search --q "owner:kim" --limit 50

owa-sites config --host contoso.sharepoint.com            # pin the SP host
owa-sites config --site owa-casa                          # pin a default site
owa-sites config --profile work                           # pin a default profile
owa-sites config --unset site                             # drop a pinned key
owa-sites config --clear                                  # delete the config file
owa-sites refresh                                         # verify SharePoint access
```

`items` and `item` require `--list`; `item` also needs an item Id (positional or
`--id`). `files` requires `--path` (a server-relative folder); `file` needs a
UniqueId (positional or `--id`). `search` requires `--q`. `--site` falls back to
the configured default site, or the tenant root when unset.

`config --unset <key>` removes a single pinned key (`profile`, `host`, or
`site`); `config --clear` deletes the config file outright.

---

## Machine / agent surface

Every owa binary exposes the same machine surface (see
[agent-integration.md](agent-integration.md) for the full contract):

- `owa-sites schema [<command>]` - JSON command schema (one command if named)
- `owa-sites --help --json` - the same schema via the help flag
- `--agent` - wrap JSON stdout in a stable `{"_owa": ..., "data": ...}` envelope
  (or set `OWA_AGENT=1`)
- `--err-json` - structured JSON errors on stderr (or `OWA_ERR_JSON=1`)
- `--doctor [--json]` - this tool's health / redaction doctor payload

---

## Notes

- **Read-only.** File download (binary `$value`) and upload
  (`Files/AddUsingPath`, which would be destructive and confirmation-gated) are
  deferred to a later phase.
- The SharePoint host is per-tenant, so it is a computed `--scope` rather than a
  named owa-piggy audience. Discovery needs one extra Graph call; pin
  `--host` to skip it.
- `search` flattens SharePoint's `Rows[].Cells[{Key,Value}]` into flat objects;
  the available keys depend on the tenant's managed properties.

See [`AGENTS.md`](../src/owa_sites/AGENTS.md) for repo layout and ground rules.
