# owa-halo

Read-only HaloITSM client. Given a ticket id or ticket URL it returns the
ticket, its status, all metadata, every action/comment, and its attachments
and inline screenshots. It never writes to Halo.

## Auth

Halo agents sign in through Entra ID SSO, but Entra is only the login
provider: Halo's own identity server issues opaque bearer tokens, so no
Microsoft token from owa-piggy works against Halo. Halo is instead a service
on the owa-piggy profile that already holds that Entra sign-in. The broker
opens Halo in the profile's Edge sidecar, lets SSO complete (it picks the
profile's account on the Entra account picker Halo forces), and keeps the
`refresh_token` cookie Halo sets. Reseed renews it with the profile's other
sign-ins:

```bash
owa-piggy clients add halo=https://norconsult.haloitsm.com --profile nc
```

`owa-halo` uses `--profile` when given, else the default profile if it has
Halo, else the only profile that does. `-A` fans out across profiles with
Halo only.

## Commands

```bash
owa-halo ticket 69296
owa-halo ticket https://norconsult.haloitsm.com/ticket?id=69296 --pretty
owa-halo ticket 69296 --all
owa-halo attachments 69296
owa-halo attachments 69296 --out ~/Downloads/halo-69296
```

- `owa-halo ticket <ticket>` prints `{id, url, summary, status: {id, name},
  ticket, actions, attachments, images}`. `ticket` and each action keep every
  field Halo returned with a value (null/empty fields are dropped).
  `--all` includes Halo system actions. `--pretty` prints a readable thread.
- `owa-halo attachments <ticket>` lists attachments (`kind: attachment`) and
  inline screenshots from the ticket body and actions (`kind: image`).
  `--out <dir>` downloads them and adds `path` to each row; existing files are
  never overwritten (exit 15).

A ticket URL must point at the profile's Halo host.

## Output and security

Inline screenshot URLs (`/api/attachment/image?token=...`) work without any
login, so they are credentials: `ticket` output rewrites each `<img src>` to
`halo-image:<n>`, matching `images[].n` and `attachments` rows. Attachment
downloads go through Halo's signed CDN links, fetched without the bearer.
Errors use the suite exit-code taxonomy (401 -> 11, 403 -> 12, 404 -> 13).
