# owa-kova

Read-only Kova schedule: your duties (shifts) at the Red Cross unit, or every
open duty with `--open`. It never signs up for or cancels anything.

## Auth

Kova signs in through Okta (`okta.redcross.no`) and keeps you signed in with
a session cookie, not a token. owa-piggy holds that session in the Edge
sidecar of the profile with the `kova` service. Sign in once; a visible Edge
window opens when there is no session yet:

```bash
owa-piggy clients add kova --profile brkh
```

Okta's "Keep me signed in" does not make its cookies survive a browser
restart, so owa-piggy pins them with an expiry and renews them on every
reseed. When the Okta session itself expires, `owa-kova` exits 11; run the
command above again.

## Commands

```bash
owa-kova schedule
owa-kova schedule --pretty
owa-kova schedule --from 2026-12-01
owa-kova schedule --open --pretty
```

`owa-kova schedule` prints one row per duty: `event`, `duty`, `start`, `end`
(local time, ISO), `when` (Kova's own text), `mine`, `my_role`, `full`,
`locked`, `past`, `event_info`, `duty_info`, `event_ref`, `crew_ref`. Kova
answers with about two months from `--from` (default today). Other members'
names and phone numbers are never included.
