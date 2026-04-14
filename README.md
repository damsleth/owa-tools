# cal-cli

Calendar CLI for Outlook / Microsoft 365. Read, create, update, and delete calendar events from the terminal.

Built for the same POSIX-util philosophy as [did-cli](https://github.com/damsleth/did-cli) - pipe-friendly JSON by default, `--pretty` for humans.

## Setup

```bash
chmod +x cal-cli.zsh add-to-path.sh
cp .env.sample .env
./add-to-path.sh   # symlinks to /usr/local/bin/cal-cli
```

## Authentication

The CLI uses a JWT from the Outlook Web App. Tokens last ~65 minutes but can be refreshed automatically.

### Automated (recommended)

One-time setup - restarts your default Chromium browser with remote debugging:

```bash
cal-cli setup
```

Then refresh tokens hands-free whenever needed:

```bash
cal-cli refresh   # ~5 seconds, no browser interaction
```

This connects to your running browser via CDP, navigates the Outlook tab to the calendar view, and intercepts the Bearer token from network traffic. Works with Vivaldi, Chrome, Edge, Brave, and Arc.

### Manual alternatives

**Bookmarklet** - add this as a bookmark, click it on `outlook.cloud.microsoft`, then click anything in Outlook. Copies the token to clipboard.

```
javascript:void((async()=>{let t=null;const of=window.fetch;window.fetch=function(...a){const[input,opts]=a;let auth=null;if(input instanceof Request)auth=input.headers.get('authorization');else if(opts?.headers instanceof Headers)auth=opts.headers.get('authorization');else if(opts?.headers)auth=opts.headers.Authorization||opts.headers.authorization;if(auth?.startsWith('Bearer ')&&!t){try{const p=JSON.parse(atob(auth.slice(7).split('.')[1]));if(p.aud?.includes('outlook.office.com'))t=auth.slice(7)}catch{}}return of.apply(this,a)};for(let i=0;i<150&&!t;i++)await new Promise(r=>setTimeout(r,100));window.fetch=of;if(t){const p=JSON.parse(atob(t.split('.')[1]));await navigator.clipboard.writeText(t);alert('Token copied! '+Math.round((p.exp-Date.now()/1000)/60)+'min left')}else alert('No token captured. Click something in Outlook, then try again.')})())
```

Then: `cal-cli login` (reads clipboard automatically on macOS).

**Interactive login** - opens Outlook, prompts for token paste:

```bash
cal-cli login
```

## Usage

```bash
# List events
cal-cli events --pretty                    # today
cal-cli events --date tomorrow --pretty    # tomorrow
cal-cli events --week 16 --pretty          # ISO week
cal-cli events --from 2026-04-14 --to 2026-04-18 --pretty
cal-cli events --search "standup" --pretty

# Create
cal-cli create --subject "lunsj" --start 11:00 --end 11:30 --category "CC LUNCH"
cal-cli create --subject "Deep work" --date tomorrow --start 13:00 --end 15:00

# Update
cal-cli update --id <event-id> --category "ProjectX"
cal-cli update --id <event-id> --start 14:00 --end 15:00

# Delete
cal-cli delete --id <event-id>

# Categories (used by DID for project/customer mapping)
cal-cli categories

# Config
cal-cli config
```

JSON output by default (pipe to `jq`). Add `--pretty` for formatted tables. Times displayed in local timezone.

## DID integration

This calendar is the data source for [DID](https://did.acmeconsulting.no) (timesheet system). Event categories determine which project/customer hours are billed to. Changing events here directly affects your timesheet.

## Dependencies

- zsh, curl, jq, python3 (all standard on macOS)
- python3 `websockets` package (for `cal-cli refresh`)

## Auth methods

| Method | Lifetime | How |
|--------|----------|-----|
| JWT via CDP (primary) | ~65 min, auto-refresh | `cal-cli setup` once, then `cal-cli refresh` |
| JWT via bookmarklet | ~65 min | Click bookmarklet + `cal-cli login` |
| OAuth via get-token | Until revoked | Requires `Calendars.ReadWrite` scope (needs tenant admin) |
