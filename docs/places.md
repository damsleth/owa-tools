# owa-places

Best-effort Outlook room and meeting-location lookup. This tool uses the
Outlook SchedulingB2 endpoint behind Room Finder, not Microsoft Graph `/places`;
it works with the existing `outlook` audience token and does not require
`Place.Read.All`.

Examples:

```bash
owa-places rooms --query Oslo --pretty
owa-places locations --limit 10
owa-places recent --query room
```

Commands:

- `owa-places rooms` lists room-like locations with an email address.
- `owa-places locations` lists normalized meeting locations.
- `owa-places recent` is an alias for `locations`.

Options:

- `--query <text>` filters normalized name, email, building, and floor fields.
- `--limit <n>` limits returned rows. The default is 25. `--limit 0` returns no rows.
- `--cv <value>` overrides the pinned SchedulingB2 correlation/version value.
- `--pretty` prints a table. JSON is the default.
- `--profile <alias>` targets a specific owa-piggy profile for this invocation;
  repeated `--profile` / `--all-profiles` fans out across profiles like the rest
  of the suite.

Output rows include `id`, `name`, `email`, `type`, `capacity`, `address`,
`building`, `floor`, and `raw`. `raw` preserves the original SchedulingB2 object
because the endpoint is undocumented and may drift.

Errors use the suite exit-code taxonomy. Because SchedulingB2 is internal to
Outlook, shape drift should be treated as a recoverable compatibility issue and
fixed in the normalizer rather than by changing the auth model.
