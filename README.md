# cal-cli

Calendar CLI for Outlook / Microsoft 365. Read, create, update and delete events from the terminal.
Pipe-friendly JSON by default, `--pretty` for humans.

```sh
brew install damsleth/tap/cal-cli
cal-cli config --refresh-token "$(owa-piggy --json | jq -r .refresh_token)" \
               --tenant-id     "$(owa-piggy --json | jq -r .tenant_id)"
```

Then

```sh
cal-cli events --pretty
```

---

## Examples

```sh
cal-cli events --pretty                       # today
cal-cli events --week 16 --pretty             # ISO week
cal-cli events --from 2026-04-14 --to 2026-04-18 --pretty
cal-cli events --search "standup" --pretty

cal-cli create --subject "lunsj" --start 11:00 --end 11:30 --category "CC LUNCH"
cal-cli update --id <event-id> --category "ProjectX"
cal-cli delete --id <event-id>

cal-cli categories
```

Pipe-friendly - JSON on stdout, logs on stderr:

```sh
cal-cli events | jq '.[].subject'
cal-cli events --date tomorrow | jq '[.[] | select(.showAs == "busy")] | length'
```

---

## Auth

Uses an OAuth2 refresh token for `outlook.office.com/Calendars.ReadWrite`.

- **With an app registration** - set `OUTLOOK_APP_CLIENT_ID` and cal-cli talks to the OAuth2 token endpoint directly.
- **Without** - cal-cli shells out to [`owa-piggy`](https://github.com/damsleth/owa-piggy), which piggybacks on OWA's public SPA client (no Azure app registration needed).

Refresh tokens rotate on every exchange and are persisted back to the config after each call. Use it once a day and it never lapses.

Config lives at `~/.config/cal-cli/config`:

```
OUTLOOK_REFRESH_TOKEN="1.AQ..."
OUTLOOK_TENANT_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
OUTLOOK_APP_CLIENT_ID=""   # optional
```

Env vars (`OUTLOOK_REFRESH_TOKEN`, `OUTLOOK_TENANT_ID`, `OUTLOOK_APP_CLIENT_ID`) override the config file.

---

## DID integration

This calendar is the data source for [DID](https://did.acmeconsulting.no) timesheets. Event categories map to projects/customers, so editing events here directly affects billed hours.

---

## Dependencies

- Python 3.8+ (stdlib only - no `pip install` required at runtime)
- [`owa-piggy`](https://github.com/damsleth/owa-piggy) unless you bring your own app registration

## Development

```sh
git clone https://github.com/damsleth/cal-cli
cd cal-cli
./scripts/add-to-path.sh       # installs via pipx
pip install -e '.[test]'       # or: pytest for dev
pytest -q
```

## Disclaimer

```
Personal tooling. Stores a delegated refresh token on disk.
If you don't know why that might be a bad idea, don't use it.
```
