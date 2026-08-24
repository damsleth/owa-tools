# owa-vids

Download Microsoft Teams / OneDrive meeting-recap video streams - a
yt-dlp-style downloader for SharePoint/OneDrive Stream recordings,
including ones where the owner disabled the download button.

The SharePoint OnePlayer streams via an MPEG-DASH manifest on a regional
`*-mediap.svc.ms` host. The whole pipeline is token-only: resolve the item's
identity, build a manifest URL with an SPO Bearer token, serially download
the fmp4 segments (SharePoint throttles concurrency hard), and mux them with
`ffmpeg -c copy`. No browser cookies, no decryption.

The `get` command fetches the DASH manifest without the `enableEncryption`
parameter, which causes the service to return clear (unencrypted) segments.
This is a property of the service, not a crack. Use only for recordings you
have legitimate access to.

## Requirements

- `owa-piggy` for auth (like the rest of the suite).
- `ffmpeg` on `$PATH` for `get` (the mux step). `info` and `check` work
  without it. Install from <https://ffmpeg.org/download.html> or
  `brew install ffmpeg`.

## Sources

Every authenticated command takes exactly one source. Just paste the
recording's URL - the kind is auto-detected:

- **The Stream "watch in browser" page** -
  `https://tenant-my.sharepoint.com/personal/user/_layouts/15/stream.aspx?id=...`.
  The file path is read from the `id` parameter.
- **The "Copy link" sharing URL** -
  `https://tenant-my.sharepoint.com/:v:/r/personal/user/.../rec.mp4?...`.
  Handed straight to Graph `/shares`.

owa-vids resolves the item's `driveId`/`itemId`/`cTag` via Graph `/shares`
and builds the `videomanifest` URL itself, so there is no DevTools step.

The media region (`*-mediap.svc.ms`) is **auto-detected** from the item's
thumbnail URLs on first use and cached per profile; `--region <host>`
overrides it. See [config](#owa-vids-config).

Two explicit source flags remain for back-compat:

- `--manifest-url '<...svc.ms/transform/videomanifest?...&format=dash>'` -
  the full manifest URL copied from DevTools (Network tab, filter
  `videomanifest`, the `application/dash+xml` request). The region is parsed
  straight from it.
- `--embed-url '<...embed.aspx?uniqueId=...>'` - the Teams/Stream player
  page URL.

## Commands

### `owa-vids info`

Probe a recording: title, duration, resolution, codecs, track/segment
counts, and region. JSON by default, `--pretty` for a human summary.
Alias: `show`.

```bash
owa-vids info 'https://tenant-my.sharepoint.com/personal/user/_layouts/15/stream.aspx?id=...' --profile globex --pretty
```

### `owa-vids get`

Download all tracks and mux to MP4. Alias: `download`.

- `--out <file>` (or `-o`) - output path; defaults to the recording's own
  title.
- `--video-only` / `--audio-only` - download a single track.
- `--workdir <dir>` - segment scratch directory (default: a per-recording
  temp dir). Already-downloaded segments are skipped, so an interrupted
  download resumes for free.
- `--pretty` - human one-liner instead of the JSON result.

Prints a JSON result line on success: `{"out": ..., "bytes": ..., "title": ...}`.

```bash
# Just paste the watch-in-browser or sharing URL
owa-vids get 'https://tenant-my.sharepoint.com/:v:/r/personal/user/.../rec.mp4?...' --profile globex -o meeting.mp4

# Explicit manifest URL still works
owa-vids get --manifest-url 'https://globex-mediap.svc.ms/transform/videomanifest?docid=...&format=dash' --profile globex
```

### `owa-vids check`

Validate auth, manifest, and the first segments of each track without a
full download. Alias: `probe`.

```bash
owa-vids check 'https://tenant-my.sharepoint.com/personal/user/_layouts/15/stream.aspx?id=...' --profile globex
```

### `owa-vids config`

View or update configuration (`~/.config/owa-vids/config`).

- `--region <host>` - pin the media region host, e.g.
  `switzerlandwest1-mediap.svc.ms`. Cached **per profile** (tenants differ
  per profile); normally auto-detected on first use, so you rarely set it.
- `--profile <alias>` - pin a default owa-piggy profile
  (`--set-profile` is accepted as an alias).

```bash
owa-vids config --profile globex --region switzerlandwest1-mediap.svc.ms
owa-vids config --profile globex
owa-vids config            # show current values (region shown per profile)
```

The region is stored in a `regions` JSON map keyed by profile; the legacy
single `region` key is still read as a fallback for pre-1.1.1 configs.

Users of the old standalone `owa-vids` script: the legacy
`~/.config/owa-vids/config.json` is migrated to the suite-standard
`KEY="VALUE"` format automatically on first run.

## Globals

- `--profile <alias>` - owa-piggy profile used to mint tokens. Repeatable
  for multi-profile fan-out on `info`/`check` (see `docs/profile-model.md`).
- `--debug` / `--verbose` - verbose HTTP / ffmpeg / auth detail (also
  `VIDS_DEBUG=1`).

## Auth notes

owa-vids is two-audience: the svc.ms manifest and segments need a
SharePoint resource token (minted as `audience=graph` with
`--scope https://{tenant host}/.default`, the same mechanism as
`owa-sites`), while identity resolution and the title fetch ride a plain
`graph` token. Mid-download the segment loop re-mints the SPO token once on
401/403, so recordings longer than a token lifetime (~80 minutes of wall
clock) download fine.

Encrypted manifests (`ContentProtection`) are rejected with a usage error -
this tool only handles the clear path and deliberately ships no decryption.
