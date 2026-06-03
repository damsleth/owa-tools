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

Every authenticated command takes exactly one source:

- `--manifest-url '<...svc.ms/transform/videomanifest?...&format=dash>'` -
  copy from DevTools while the recording plays: Network tab, filter
  `videomanifest`, the `application/dash+xml` request, Copy URL. The media
  region host is parsed from this URL and cached for later runs.
- `--embed-url '<...embed.aspx?uniqueId=...>'` - the Teams/Stream player
  page URL. Needs the media region: it's cached automatically the first time
  you use a `--manifest-url`, or pass `--region <host>` once.

## Commands

### `owa-vids info`

Probe a recording: title, duration, resolution, codecs, track/segment
counts, and region. JSON by default, `--pretty` for a human summary.
Alias: `show`.

```bash
owa-vids info --manifest-url 'https://swon-mediap.svc.ms/transform/videomanifest?docid=...&format=dash' --profile swon --pretty
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
# Manifest-URL path
owa-vids get --manifest-url 'https://swon-mediap.svc.ms/transform/videomanifest?docid=...&format=dash' --profile swon -o meeting.mp4

# Embed-URL path (region must already be cached or --region passed)
owa-vids get --embed-url 'https://tenant-my.sharepoint.com/personal/user/_layouts/15/embed.aspx?uniqueId=...' --profile swon
```

### `owa-vids check`

Validate auth, manifest, and the first segments of each track without a
full download. Alias: `probe`.

```bash
owa-vids check --manifest-url 'https://swon-mediap.svc.ms/transform/videomanifest?docid=...&format=dash' --profile swon
```

### `owa-vids config`

View or update configuration (`~/.config/owa-vids/config`).

- `--region <host>` - pin the media region host (tenant-wide), e.g.
  `switzerlandwest1-mediap.svc.ms`.
- `--profile <alias>` - pin a default owa-piggy profile
  (`--set-profile` is accepted as an alias).

```bash
owa-vids config --region switzerlandwest1-mediap.svc.ms
owa-vids config --profile swon
owa-vids config            # show current values
```

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
