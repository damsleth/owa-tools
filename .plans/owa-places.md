# owa-places

_Created 2026-06-01_

## Feasibility — VERDICT: VIABLE (revised 2026-06-01) — via Outlook SchedulingB2, NOT Graph /places

Reversed after dead ends:
- **Graph Places API** (the rich, official one: `/places` + building/floor/section/
  desk/workspace/room hierarchy, per learn.microsoft.com places-api-overview) →
  **401 on ALL endpoints** (`/places`, `…graph.building`, `…graph.room`,
  `…graph.desk`, beta too), re-probed 2026-06-01 AFTER Places was enabled in the
  tenant. It needs `Place.Read.All`, which is NOT in the One Outlook Web client's
  fixed scope set → permanently unavailable. (Enabling buildings via
  `Set-PlacesSettings` doesn't help — it's a scope gate, not a setup gate.)
- Outlook REST v2.0 `/me/findrooms` → removed (`RequestBroker--ParseUri`).

So the rich buildings/floors/desks hierarchy is OFF the table; the viable door
below gives the narrower room / meeting-location surface (what Room Finder uses).

LIVE DOOR: the new Microsoft Places UI (`outlook.office.com/hosted/places`) is
backed by the **Outlook SchedulingB2 API**, which rides the **`outlook` audience we
already mint** (owa-cal/owa-mail use it — zero new auth, no owa-piggy change).

Auth CONFIRMED working (probed 2026-06-01, dno):
`POST https://outlook.office.com/SchedulingB2/api/v1.0/me/initmeetinglocations`
with an outlook-audience bearer:
- GET → **405** (it's a POST, not GET)
- POST `{}` / `{"n":12}` / `{"NumberOfLocations":12}` → **400** BadRequest (wrong body — but PAST AUTH)
- POST no body → **411** Length Required
Never 401/403 → **the token is accepted**. The only remaining gap is the exact
request payload (an undocumented internal DTO that guessing won't match).

## OPEN: capture the real request shape (the one concrete blocker)
- [ ] From browser devtools Network tab on
      `https://outlook.office.com/hosted/places?hostApp=teams`, capture the exact
      `initmeetinglocations` POST body + headers, and enumerate sibling SchedulingB2
      endpoints (rooms / room-lists / buildings / floors). Places exposes more than
      just initmeetinglocations.

## Steps (once payload captured)
- [ ] Scaffold `src/owa_places/` per docs/new-tool-onboarding.md. Audience: `outlook`
      (named, already supported). Base: `https://outlook.office.com/SchedulingB2/api/v1.0`.
- [ ] `api.py`: `get_token(audience='outlook')`; `http.request('POST', url, body=...)`
      with the captured payload + a pinned `cv` correlation param.
- [ ] Commands (per discovered endpoints): `rooms`, `locations`/`recent`, plus
      building/floor lookups if SchedulingB2 exposes them.
- [ ] Normalizers (location: name, address, capacity if present), `--pretty` table,
      full onboarding test set (mock the SchedulingB2 boundary), all registrations.
- [ ] Acceptance per onboarding doc.

## Notes
- Internal/undocumented API (SchedulingB2) → weaker stability contract than Graph.
  Tolerate shape drift, document as best-effort, pin a `cv`. This is the trade for
  there being NO delegated Graph Places scope on the OWA client.
- Same `outlook` token owa-cal/owa-mail already use — the cheapest possible auth.
