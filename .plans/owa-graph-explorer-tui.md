# owa-graph-explorer-tui

_Created 2026-06-01 · multi-audience/FOCI · multi-agent workflow plan · self-review round 1 (62-agent workflow, 49 gaps) + round 2 (5 parallel reviewers): fixed `_fetch_page` header-access contradiction, case-insensitive continuation header, `TokenInfo.scopes` source, first-mint/`curses.wrapper` lifecycle, stderr-teardown owner, `MANIFEST.in`→pyproject package-data, unowned test fixtures, output-mode-flag rejection, schema alias, atomic-guard boundary._

## ⚠ ARCHITECTURE UPDATE (2026-06-15) — now the flagship `tui_kit` adapter

**Decision (2026-06-15): this is no longer a standalone mail-pattern copy. It is the
flagship/most-complex adapter on the shared `owa_core/tui_kit/` extracted by
[owa-suite-tui-rollout.md](owa-suite-tui-rollout.md) Step 0.** That reframes the
scaffolding layer of this plan; the **domain cores below stay valid as-is** and are
exactly the parts `tui_kit` does NOT absorb:

- **KEEP unchanged** — the genuinely graph-specific reasoning: the curses-safe
  boundary invariant, Phase 1 A1 (per-audience nav engine: pagination shapes, link
  heuristics, template normalization, tiers) and A2 (FOCI token-cache + `_ensure_token`
  + settings), the audience model, and Phase 3 CLI wiring incl. the `modes.py`
  `--profile` guard fix.
- **SUPERSEDED by `tui_kit`** — the generic scaffolding this plan told C1 to build
  from scratch: the event loop, list/detail draw helpers, resize/redraw, the esc-menu
  state machine, view-settings cycle, and the test harness. These now come from
  `tui_kit.{app,layout,menu,settings,keys}`, parameterized by callbacks. Specifically:
  - **DO NOT** "re-implement `tui_menu.py`" (Phase 2) — use `tui_kit.menu` with a
    graph title + items list passed in. The mail-coupling that motivated re-implementation
    is gone once the menu is generic in the kit.
  - **DO NOT** extract `FakeScreen` into a graph-local `conftest` — `tui_kit` ships the
    shared test harness; import it.
  - C1's Phase 2 work shrinks to **graph-specific callbacks** fed to `tui_kit.app`:
    `fetch_items` (wraps A2 `_ensure_token` + A1 `_fetch_page` — this is where the
    curses-safe invariant is enforced), `render_row` (A1 `build_rows`), `render_detail`
    (the per-tier/`format_pretty`-graph-gated detail logic), and the graph `actions`
    set (`a` audience-switch, `/` jump, `e` query, `n` page, `r`, `c`/`y`, `o`, `m`, `D`).
- **PREREQUISITE:** `tui_kit` Step 0 must land and freeze its callback contract before
  Phase 2 here starts. Phase 0/1 (data table, nav engine, auth-cache) are **independent
  of the kit** and can proceed in parallel with Step 0. **`tui_kit.app`'s contract must
  be curses-safe** to honor this plan's invariant — its `fetch_items` callback returns a
  status/result without printing or raising; confirm this when freezing the contract.

The phase text below predates this decision; where it conflicts with the four bullets
above, the bullets win.

---

## Goal

Add an interactive, dependency-free curses TUI to `owa-graph` (`owa-graph tui`,
alias `explore`) that navigates/drills into **every FOCI audience owa-piggy can
mint a token for** — not just Microsoft Graph — on the caller's own family
refresh token (FRT). Land on a service, see the response, drill into collections
and nested links, hop audiences.

**FOCI is the unlock — but it's bounded.** owa-piggy holds one FRT and redeems it
per-audience via `grant_type=refresh_token` (scope `<resource>/.default`). So an
audience hop needs no re-auth prompt. **But reach is gated by what the pinned One
Outlook Web client `9199bf20` preauthorizes**: resources it doesn't preauthorize
return `AADSTS65002` (StaffHub/Tasks/Project are walled off), and per-profile
Conditional Access can block others (`AADSTS53003`) — see memory
`owa-piggy-token-scope-limits`. The TUI must therefore treat per-audience failure
as a first-class, graceful state, not an exception.

**Self-review root cause (drives the whole workflow).** owa-graph's `api`/`auth`
layer is **not curses-safe**: `api.api_request` re-raises
`AuthExpiredError`/`ScopeInsufficientError` on 401/403 (`api.py:61-62`) and
`emit_error`s to stderr on every other failure (`api.py:81-90`); `auth.setup_auth`
raises unguarded (`auth.py:75-80`); owa-piggy/`http` debug paths `print` to stderr.
Any of these mid-loop aborts the TUI or scribbles over the frame — defeating the
"degrade gracefully" promise. The mail TUI never hits this because it mints once
before `curses.wrapper` and never re-mints. **The cross-cutting invariant below is
the spine of the build.**

**Corrected expectations (were wrong in earlier drafts):**
- Audience switch is **not "instant/free."** owa-piggy's `--json` path bypasses
  its own access-token cache (`owa-piggy/cli.py:419`), so every cache-miss hop is
  a live AAD round-trip (~200–800 ms) **with FRT rotation** (`token_flow.py:106`).
  The TUI's *own* exp-aware per-audience cache is therefore load-bearing, and a
  "minting token for <audience>…" status must precede the blocking subprocess.
- `api_mod.paginate` only follows `@odata.nextLink` — it silently truncates ARM
  (`nextLink`), DevOps (`x-ms-continuationtoken` header), etc. Pagination needs a
  per-audience continuation switch.
- Non-JSON/Tier-D bodies can't reach an "opaque" classifier through the normal
  path — `http._decode_response` raises `InternalError` on non-JSON first. Must
  fetch with `raw=True` and `json.loads` ourselves.

## Cross-cutting invariant — the curses-safe boundary (applies to every phase)

Inside `curses.wrapper`, the ONLY permitted terminal writes are via `_safe_addstr`
or to `state.status`. No code path may `print`, `emit_error`, or hit
`sys.stderr`/`sys.stdout` un-redirected. Concretely:
- **Never** call `api_mod.api_request`, `auth_mod.setup_auth`, or
  `auth._refresh_via_owa_piggy` from inside the loop. Use the two wrappers below.
- `tui_nav._tui_get(url, token, *, debug) -> (status_kind, FetchResult | str)`
  wraps `owa_core.http.request(..., raw=True)` directly, catches every `OwaError`,
  never raises/prints. `status_kind ∈ {ok, auth, scope, notfound, ratelimit, error}`
  (mapped from the exception type — `http` raises on non-2xx and discards the body).
  On `ok` the second element is a `FetchResult(status:int, headers:dict, body:bytes)`
  (frozen dataclass) — it **must carry headers**, because DevOps pagination reads
  `x-ms-continuationtoken` from the response header, not the body; on non-`ok` it's
  the redacted error message string. Always fetched `raw=True` so `.json` decoding
  can't raise inside the loop — `classify_response`/`_fetch_page` do `json.loads`
  themselves (this is also what makes the `opaque` kind reachable).
- `_ensure_token(audience, state) -> TokenInfo | None` calls
  `owa_core.auth.get_token_for_config(state.config, …)` (not `setup_auth`) inside
  `try/except OwaError`; on failure sets `state.status`, returns `None`, and
  **evicts** `token_cache[audience]` so `r`/retry is meaningful. On success returns
  the `TokenInfo` AND atomically updates `state.token/api_base/scopes/exp_epoch`
  (per-audience `api_base` and `scopes` are needed by fetch + graph annotation, so
  a bare token string is insufficient — see Phase 1 A2).
- **owa-piggy is only ever invoked via `--json`** (`get_token_for_config`), which
  `capture_output=True` and **never prompts interactively** — a stale/`AADSTS700084`
  FRT surfaces as a captured-stderr `AuthExpiredError`, handled by `_ensure_token`.
  The TUI must never shell `owa-piggy setup`/`reseed` (those prompt and would
  corrupt the frame).
- **stderr redirect — owned by `run()`, not the loop.** `run()` does
  `old=sys.stderr; sys.stderr=state.stderr_buf (io.StringIO); try: curses.wrapper(_loop, state); finally: sys.stderr=old`.
  Suppress `debug=True` on in-loop mints (`owa_core/auth.py:131,220` print to stderr).
  `_loop` wraps each iteration's fetch/render in `try/except Exception` → write the
  traceback to `state.stderr_buf` + set `state.status`, so an unexpected non-`OwaError`
  (a `build_rows` `KeyError`, a stray `curses.error`) keeps the TUI alive instead of
  escaping into a dead buffer; `KeyboardInterrupt`/`SystemExit` propagate (wrapper
  restores the terminal, `finally` restores stderr).
- This invariant is **Agent R1's** primary audit target at the final gate.

## Audience model

**Key-set sync, NOT value-sync.** `owa_graph/auth.py:AUDIENCE_API_BASE` has 13 of
owa-piggy's 17 `KNOWN_AUDIENCES`; add `ic3` (`https://ic3.teams.office.com`),
`csa` (`https://chatsvcagg.teams.microsoft.com`), `presence`
(`https://presence.teams.microsoft.com`), `uis` (`https://uis.teams.microsoft.com`).
Only the **key set** must equal `KNOWN_AUDIENCES`; the base-URL **values are
owa-graph-owned** and intentionally differ (e.g. powerbi: AAD audience host
`analysis.windows.net/powerbi/api` vs request base `api.powerbi.com/v1.0`). A
literal value-sync would 404 powerbi. The completeness test asserts key-set
equality only.

**Explorability tiers** (drive per-audience UX + seeds):
- **A — self-describing OData/discovery:** graph (manifest+navLinks), outlook/outlook365 (OData v2.0), azure (ARM `nextLink`), powerbi.
- **B — REST with collections (response-driven):** flow/PowerApps, manage, substrate, devops (`_apis`, continuation header).
- **C — opaque internal Teams APIs (seed paths only):** teams, ic3, csa, presence, uis.
- **D — data-plane, not browseable:** keyvault, storage, sql — raw-request targets, footer banner, no faked hierarchy.

`data/audience_seeds.json` (new, ships in Phase 0) gives each of the 17 audiences
1–3 entry paths; graph adds the `paths.json.gz` overlay.

---

## Orchestrated multi-agent build

**Convention:** model **sonnet** unless flagged **OPUS**. Opus is reserved for the
two correctness-critical cores (nav engine, auth/cache) and the final adversarial
review. Each phase ends at a **gate** (named tests) that must pass before the next
starts. File ownership is **region-disjoint and phase-sequenced** — a couple of
files (`cli.py`, the completion scripts) are touched in two phases but in
non-overlapping regions, never concurrently; the genuinely parallel pair (Phase 1
A1/A2) owns wholly disjoint files.

### Phase 0 — Foundation _(Agent F0, sonnet)_ — ships independently, gates everything
_Rationale: pure-data + table edits, no hard reasoning._
**Owns:** `auth.py` (table only), `src/owa_graph/data/audience_seeds.json` (new),
`tests/graph/test_audience_table.py` (new), `cli.py:print_help()` (audience prose only),
`completions/owa-graph.{bash,zsh,fish}` (audience list), `docs/graph.md` (audience prose), `owa_core/jwt.py` (add `tenant_id`).
- Add ic3/csa/presence/uis to `AUDIENCE_API_BASE`; add `AUDIENCE_DESC` (one-liners mirroring `owa-piggy audiences`).
- Create `audience_seeds.json` under `owa_graph/data/`: object keyed by audience short-name, value = `[{path,label,note?}]`. Tier A/B from known paths (graph→me/users/groups, outlook→me/messages, azure→subscriptions, devops→_apis/projects, powerbi→myorg/datasets, manage→`{tenant_id}`/ServiceComms/CurrentStatus, flow→…, substrate→cf/v2/me); Tier C curated Teams paths; Tier D raw placeholders. **Packaging:** there is NO `MANIFEST.in` in this repo — data ships via `pyproject.toml [tool.setuptools.package-data] owa_graph = ["data/*.json", "data/*.json.gz"]`, whose `data/*.json` glob **already matches** the new file. No `pyproject` edit needed; just land the file in `owa_graph/data/` (the `owa_graph.data` package is already declared).
- Add `jwt_mod.tenant_id(token)` (decode `tid` claim) for `{tenant_id}` seed resolution AND for the session header (Phase 2); fallback literal `myorganization`.
- Expand the audience list 13→17 in all three completion scripts, in `print_help()` (grep the "13"-audience `Known:` prose — it's in the help body, not at a fixed line), and in the `docs/graph.md` "13 known FOCI audiences" prose.
- **Gate:** `test_audience_table.py` green — `set(AUDIENCE_API_BASE) == _KNOWN_PIGGY_AUDIENCES` (frozenset **literal**, NOT imported from owa_piggy — installed version may lag; **required** dated comment citing the owa-piggy version snapshotted, e.g. `# owa-piggy 0.7.x scopes.py:KNOWN_AUDIENCES`); parametrized `resolve_api_base(k).startswith('https://')` over all keys; `--beta`-warns for the 4 new audiences; every audience has ≥1 seed. **Must be green before any other phase.**

### Phase 1 — Parallel core build _(two independent OPUS agents, wholly disjoint files)_
**Freeze the shared contract first (one paragraph), so neither agent edits the other's symbols and C1 never re-touches the dataclass:**
- `FetchResult(status, headers, body)` lives in `tui_nav.py` (A1-owned).
- `TokenInfo(token, scopes, api_base, exp_epoch)` and the **complete `_State` field set** live in `tui.py` (A2-owned). `_State` carries: `config, audience, api_base, token, scopes, exp_epoch, token_cache (dict audience→TokenInfo), path, query, response, kind, rows, selected, top, detail_lines, next_link, history (list of 7-tuples), status, settings, menu_open, overlay (None|'audience'|'bookmarks'|'help'|'debug'), stderr_buf, debug`. A2 ships this **final** shape; C1 only adds methods/draw code, never new fields.
- A1 imports nothing from A2; A2 imports nothing from A1; C1 imports `FetchResult` from `tui_nav` and uses A2's `_State`/`_ensure_token`.

**Agent A1 — nav engine (OPUS)** — _Rationale: the hard, correctness-critical core: per-audience pagination/path shapes, link heuristics, template normalization._
**Owns:** `src/owa_graph/tui_nav.py` (new) and `src/tests/graph/conftest.py` (new — the response-payload fixtures its own gate needs) — pure, no curses.
- `_tui_get` (curses-safe wrapper, see invariant) — never raises/prints; returns `(status_kind, FetchResult(status, headers, body))`. Headers are part of the contract.
- `classify_response`: `json.loads(result.body)` ourselves; on `JSONDecodeError` → `kind='opaque'` keeping raw bytes (the ONLY way opaque is reachable — `api_request`/`http` raise `InternalError` on non-JSON first and discard bytes).
- `build_rows`: collection labels (best human field); **caps** `MAX_ROWS=500`, `MAX_KEYS=100`, dimmed "… N more (n to page)" sentinels; empty `value:[]` → single read-only "(no items)" row (mirrors mail tui.py:224); opaque → single **non-drillable** sentinel (`drillable=False`; Enter is a no-op).
- `next_path(current_path, item)`: three id-shapes — absolute URL → navigate by full URL; absolute path starting `/` (ARM `id` like `/subscriptions/{s}/resourceGroups/{g}`) → **replace** path (do NOT append); relative segment → append.
- Link-field rules: **deny-list** `@odata.context/editLink/metadata/type/etag/count`; **same-host** filter for `^https?://` values (cross-host CDN/photo/portal URLs → detail pane only); add `*@odata.associationLink` + bare `nextLink` alongside `*@odata.navigationLink`/`@odata.nextLink` as drillable patterns. (ARM `resourceTypes` deep-parse deferred post-v1 — note as known limit.)
- `_fetch_page(audience, url, token) -> (payload, next_cursor)`: calls `_tui_get` internally and **binds `result`** so it can read both body and headers (the earlier `(audience, url, token)`-only signature could not reach headers — fixed). `_CONTINUATION_SHAPE` dict: OData (graph/outlook/outlook365/powerbi/flow/manage/substrate)→`payload['@odata.nextLink']`; ARM (azure/keyvault/storage/sql)→bare `payload['nextLink']`; devops→continuation token from `result.headers` via a **case-insensitive** lookup (`_headers_dict` preserves the server's casing, so a plain `.get('x-ms-continuationtoken')` can miss `X-MS-…`) re-appended as `?continuationToken=`. Default `odata`. **Do NOT use `api_mod.paginate`** (eager + `@odata.nextLink`-only).
- Graph prefix-index `Dict[str, List[str]]` from `all_paths('v1.0')` (key=normalized all-but-last prefix, `''` for top-level; values verbatim incl `{var}`); template-normalize current path (substitute `{var}` when a GUID/id-shaped literal misses) so `me/messages/<uuid>`→`me/messages/{id}`. `None` for non-graph audiences (skip overlay; callers must tolerate `None`). Scope annotation graph-only (`scopes.required_scopes` ∩ `state.scopes`).
- **Gate:** `tests/graph/test_tui_nav.py` green against `conftest.py` fixtures: GRAPH_COLLECTION (`@odata.nextLink`), ARM_SUBSCRIPTIONS (bare `nextLink`), TEAMS_OPAQUE (valid JSON, no top-level `value`), TIER_D_SCALAR, **plus a non-JSON `bytes` body** (exercises `classify_response`'s `JSONDecodeError → kind='opaque'` branch — the JSON-shaped fixtures don't), a devops response with `X-MS-ContinuationToken` header (case-insensitive lookup), literal-vs-template prefix collision (`/users`+`/users/me`+`/users/{id}` → two rows, `manager` excluded), and ARM absolute-id path-replace.

**Agent A2 — auth/token-cache + settings (OPUS)** — _Rationale: the FOCI/cache layer + curses-safe error boundary the whole TUI's stability rests on._
**Owns:** `tui_settings.py` (new), `config.py` (ALLOWED_KEYS only), and `tui.py` **created** with the final `_State` dataclass + `TokenInfo` + standalone `_ensure_token` (only those symbols; C1 fills the rest in Phase 2 — sequential hand-off on one file, not concurrent).
- Extend `config.py:ALLOWED_KEYS` with 7 keys: `graph_tui_reading_pane`, `graph_tui_split_ratio`, `graph_tui_pretty_json`, `graph_tui_scope_warnings`, `graph_tui_default_audience`, `graph_tui_default_path`, `graph_tui_bookmarks` (config_set raises `ValueError` on unknown keys).
- `tui_settings.py` mirroring `owa_mail/tui_settings.py`: `READING_PANE_VALUES=('right','bottom','off')`, `SPLIT_RATIO_VALUES`, frozen `Settings`, `_FIELD_TO_KEY`, `from_config`/`to_config_dict`. Bookmarks = JSON-encoded list of `{audience,path,label}` in one config string; persist only `(audience,path,label)`, never bodies.
- `TokenInfo(token:str, scopes:frozenset[str], api_base:str, exp_epoch:int)`. `_ensure_token(audience, state) -> TokenInfo | None`: cache hit if `time.time() < info.exp_epoch-60`. On miss: set `state.status='minting token for <audience>…'` + redraw footer **before** the blocking `subprocess.run(timeout=60)`; call `get_token_for_config(state.config, …)` (carries `expires_at`/`expires_in`; `setup_auth` discards them) + `resolve_api_base(audience)` (safe in-loop: no print/raise for known audiences with `beta=False`) inside `try/except OwaError`; on failure set status, evict, return `None`. Populate `TokenInfo.scopes` from **`jwt.scopes_in_token(token.access_token)`** (the `scp` claim — matches `scopes.required_scopes` names; the broker `scope` string from the `.default` flow is the *requested* `<resource>/.default`, which won't intersect). `exp_epoch` is **always a concrete int**: `expires_at` is `int|None` from the broker, so coerce — `expires_at or (time.time()+expires_in)`, falling back to a short fixed TTL if both absent (guards `time.time() >= None-60` TypeError in-loop).
- **Gate:** `tests/graph/test_tui_auth.py` green — cache-hit-no-double-mint, FOCI-failure→`None`+status (monkeypatch must `raise AuthExpiredError`; the real fn never returns None), per-audience keying, exp-expiry forces re-mint, `expires_at=None` doesn't raise (TTL fallback), `TokenInfo` carries `api_base`+`scopes`.

> A1↔A2 run concurrently (disjoint files). Phase 2's C1 extends A2's `tui.py` sequentially.

### Phase 2 — Curses front-end _(Agent C1, sonnet; R1 scrutinizes the divergent bits)_ — fan-in on Phase 1
_Rationale: drawing mirrors the proven owa-mail template (pattern-following). **But** the audience-divergent parts — the `run()` signature/lifecycle, `format_pretty` graph-gating, history/cache invalidation — are correctness traps a pattern-follower can miss; these are R1's focus and may be escalated to opus if C1 stumbles._
**Owns:** `tui.py` (draw+loop + lifecycle, extending A2's stub), `tui_menu.py` (new), and the `FakeScreen` extraction into `src/tests/conftest.py` (today it lives inline in `src/tests/mail/test_tui_loop.py:14,52`) + the one-line edit to the mail test to import it from there.
- **`run()` lifecycle (the last place the invariant can break).** `run(config, *, start_audience='graph', start_path=None, debug=False)` — **deliberately omits** `access_token`/`api_base` (contrast mail's `run(config, access_token, api_base,…)` tui.py:606; graph re-mints per audience). It builds `_State`, sets up the stderr redirect (per invariant), and enters `curses.wrapper(_loop, state)`. **The initial mint + first fetch happen INSIDE the first loop iteration**, not before `curses.wrapper`: the first `_draw_*` shows an empty list + `state.status='minting token for <audience>… / fetching…'`, then `_ensure_token(start_audience)` + first `_fetch`. A failed seed (graph `/me` 401, `AADSTS65002/53003`) lands as `state.status` + empty list with the audience switcher (`a`) reachable — **never a clean exit** (graceful degradation is the whole point; this inverts mail, which mints before the loop and exits cleanly on a seed 401).
- `_loop` + `_draw_header/_list/_detail/_help/_debug` + `_safe_addstr` + `_prompt`. `height,width = stdscr.getmaxyx()` fresh at top of every `_draw_*` (never cache); loop branch `if ch == curses.KEY_RESIZE: curses.resizeterm(*stdscr.getmaxyx()); stdscr.clear(); continue` (mirror into owa_mail `_loop` as cleanup).
- Header shows `audience · profile · tenant` (`jwt_mod.tenant_id` from Phase 0) so per-profile CA failures are diagnosable. Profile is **fixed for the session** (parity with mail TUI; in-TUI switcher deferred — see Open decisions).
- Detail pane branches on `state.kind`/audience: `format_mod.format_pretty` **only when `audience=='graph'`** (its `_looks_like_users`/`_looks_like_messages` greedily mislabel ARM/devops as a users table — keep the gate strictly `== 'graph'`, never widen to "Tier A"); else `json.dumps(payload, indent=2, ensure_ascii=False)`. Opaque: hex preview of first 4 KB (`binascii`) for bytes / `str(payload)` for scalars — never `format_pretty`. Tier-D `{keyvault,storage,sql}` → persistent footer "Tier D: raw target — not a browse surface  [r]efetch [y]ank [c]url".
- Perf: cache pre-wrapped `detail_lines` on `_State` (recompute once per fetch/pane-resize), redraw slices `detail_lines[top:top+h]` (O(visible)); `MAX_DETAIL_BYTES=65536` slice before wrap. Cache `rows` by `(audience,path)` key.
- History frame = `(audience, path, query, selected, top, rows, next_link)`; `h`/Backspace restores all seven with **no** network call; `r` re-fetch clears `next_link`, resets top/selected, discards cached rows for the **current level only**.
- Keybindings (each must have a spec; degenerate cases below):
  - j/k/u/d/g/G move; Enter/l/→ drill; h/←/Backspace pop; `q` quit; Esc menu.
  - **`a`** audience switcher (overlay of 17 with desc+tier → `_ensure_token` → seed path). On a failed switch (seed 401/`AADSTS`), **commit** the audience (so `r` retries it), show empty list + status — do **not** silently revert, or the user can't tell the switch was attempted.
  - **`/`** jump-to-path: prompt for a path. Graph → manifest completion; non-graph → free-text, **no** completion (tolerate the `None` prefix-index, don't crash). A failed jump (404 / unknown path) sets `state.status` and does **not** push history or replace `rows` (stay on the prior valid view).
  - **`e`** edit query: OData audiences → `$select/$top/$filter/$expand`; non-OData/Tier-D → raw `?k=v` only. Persisted into `state.query` + the history frame.
  - **`n`** next page via `_fetch_page` (uses `state.next_link`).
  - **`r`** re-fetch the current path (re-mints via `_ensure_token` if expired; locked lowercase — see Open decisions).
  - **`c`** / **`y`** operate on the current **URL + token only**, never `payload`/`body` — so they are safe on every tier including opaque/Tier-D. `c` = `emit_mod.render_curl(method, url, state.token, include_token=False)` (token is a **required positional**; `include_token=False` emits the `$OWA_TOKEN` placeholder — never pass `True`). `y` = yank URL.
  - **`o`** open in browser: graph → build `https://developer.microsoft.com/graph/graph-explorer?request=<path>&method=GET&version=v1.0` (new builder); **all other audiences → `state.status='no browser target for <audience>'` and no-op** (never `webbrowser.open` a raw API URL — returns JSON/401, useless; also no-ops cleanly headless/over-SSH).
  - **`m`** bookmark `(audience, path)`.
  - **`D`** debug-log overlay (spec below).
- `HELP_LINES` multi-line constant (grouped Navigation/Audience/Query/Clipboard-Bookmarks/General) + `HELP_LINE`/`PANE_HELP_LINE` footer constants (mirror tui.py:39-44). `Help` opens a scrollable `_draw_help` overlay reusing `_draw_reader` scroll mechanics. **`_draw_debug`** is spec'd the same way: renders `state.stderr_buf.getvalue().splitlines()` with `_draw_reader` scroll mechanics (j/k/u/d scroll, q/Esc close) — it must scroll, since several debug mints can exceed a screen.
- `tui_menu.py` **re-implemented** (NOT imported from mail — it hardcodes `'owa-mail'` title + mail settings fields): copy the generic nav state machine (`move/select/back/open_settings`) verbatim; `_TITLE_LINES=['owa-graph','─'*16]`; `_TOP_ITEMS`= Resume/Audiences/Settings/Bookmarks/Help/Quit; `_get_settings_meta` over `owa_graph.tui_settings`; drop `date_custom`. Copy `_pad`/`_truncate`.
- **Gate:** `tests/graph/test_tui_loop.py` green via shared `FakeScreen` (from `src/tests/conftest.py`) + `_no_terminal` autouse fixture; monkeypatch `_ensure_token`/`_fetch`: first-iteration mint+fetch, seed-failure→status (no exit), j/k nav, Enter/l drill+history-push, h/Backspace pop-restores, `a` overlay→audience change (success **and** failed-switch-commits), `n` nextLink, `/` failed-jump-keeps-view, Esc toggle, `D` overlay scrolls, `q` quit, KEY_RESIZE no-crash.

### Phase 3 — CLI wiring _(Agent W1, sonnet)_ — needs `tui.run` to exist
_Rationale: mechanical argv/dispatch/schema wiring against an existing pattern._
**Owns:** `cli.py` (dispatch, `cmd_tui`, schema, `main()`, `_cmd_internal_complete`), `owa_core/modes.py` (`command_name` hardening — shared core), `completions/owa-graph.{bash,zsh}` (verb additions only).
- **ONE ATOMIC DIFF** (any partial state lets `--agent tui` reach curses — and the `modes.py` fix is a **co-requisite**, not a separate step, because the Phase-3 gate's `--agent --profile work tui` test fails without it):
  - Define `_TUI_FLAGS = [--audience <name>, --path <p>]`. `cmd_tui` with `from owa_core import tty as tty_mod` + `if not tty_mod.is_interactive(): raise UsageError(...)` (owa_core/tty.py:7; mirrors owa_mail/cli.py:17,963); parse `--audience` (validated against `AUDIENCE_API_BASE` → `UsageError('Unknown audience…')`) + `--path`; **reject every other flag** (incl. the suite's reflexive `--pretty`/`--ndjson`/`--raw`) via the flag loop's `else: UsageError`. Forward `debug=_debug_enabled(config)` (folds in `--debug` + `GRAPH_DEBUG`); `--profile` needs no extra threading — `_main` already writes it into `config['owa_piggy_profile']` (cli.py:774-775) and `get_token_for_config` reads it from config.
  - Dispatch `tui`/`explore`→`cmd_tui` **before** the verb fallthrough; `RESERVED_SUBCOMMANDS |= {'tui','explore'}`.
  - Schema: `schema_mod.command('tui', 'Explore any FOCI audience interactively', auth='graph', interactive=True, aliases=('explore',), flags=_TUI_FLAGS)` — use the established `aliases=` mechanism (schema.py `resolve_alias`, as owa-drive does) rather than a duplicate `explore` command, so `--schema`/`--help` show one row with the real flag surface. `interactive_commands=('tui','explore')` still lists **both literal names** (modes.py matches the raw command token, not the schema-resolved one) on the EXISTING `run_with_output_modes` call (cli.py:820-823 currently passes none — `interactive=True` alone does NOT block the agent path).
  - **`command_name` hardening (the co-requisite).** `owa_core/modes.py:command_name` (lines 33-39) returns the first token not starting with `-`, but `--profile` takes a *value*: `owa-graph --agent --profile work tui` → `command_name` returns `work`, the guard at `modes.py:119` misses, `_main` strips `--profile work` and launches curses **under `--agent`**. Fix: add `_GLOBAL_VALUE_FLAGS = {'--profile'}` (the one suite-wide global that takes a value; `--audience` is per-command and always follows the command, so it's not global) and skip the flag **and its value**, guarding against `--profile` as the last token (no value → don't `IndexError`). Strictly more correct everywhere (envelope `command`/`OWA_COMMAND` stop mis-resolving to the profile alias) and **closes the identical hole for `owa-mail tui`** (shares `--profile`). Mirrors the tool-local precedent at `cli.py:714 _first_nonglobal`.
- `_cmd_internal_complete`: add an `audiences` branch (parallel to `paths`); wire `__complete audiences` dynamically in both completion scripts (single-source). Add `tui`/`explore` to the `reserved` arrays + first-positional block.
- **Gate:** `tests/graph/test_tui_cli.py` green — refuses-non-interactive; launches-with-`--audience` (forwards `start_audience`), default `graph`, `--path` forwarded; `UsageError` on unknown flag, unknown audience, **and `--pretty`/`--ndjson`**; `owa-graph --agent tui` AND **`owa-graph --agent --profile work tui` / `… explore` refuse** (assert the curses loop is never reached); `owa-graph --schema` lists `tui` interactive with `explore` as its alias and the `_TUI_FLAGS` surface. Plus `tests/core/test_modes.py`: `command_name(['--profile','work','tui'])=='tui'`, `command_name(['--profile'])==''` (no IndexError), envelope `command` resolves to `tui` not `work`; and a **mail-side** assertion that `owa-mail --agent --profile work tui` refuses.

### Phase 4 — Docs, version, adversarial review _(Agent D1 sonnet + Agent R1 OPUS)_
**D1 (sonnet)** — _Rationale: prose + version bump, low risk._
**Owns:** `docs/graph.md` (Interactive explorer section), `pyproject.toml` (version), `tests/core/test_version.py:36`.
- docs: keybindings table (incl. "Differences from owa-mail TUI": `r`=re-fetch not read-toggle, audience switcher, per-tier `o`/`e` behavior; `HELP_LINES` verbatim), FOCI/audience-switch explanation (bounded reach + `AADSTS65002`), tiers, scope-warning + Tier-D caveats, the fixed-profile/tenant header note.
- **Two atomic items:** bump `version` in `pyproject.toml`; update the hardcoded string at `test_version.py:36` (currently `0.6.0`) — failing the second fails CI.
- **Gate:** full `pytest src/tests` green.

**R1 — adversarial final review (OPUS)** — _Rationale: closing correctness gate; reasons across all phases for curses-corruption + FOCI-failure-path holes unit tests miss._
**Owns:** nothing (read-only; files findings back to the owning phase).
- Audit the **curses-safe invariant**: no path inside `curses.wrapper` calls `api_request`/`setup_auth`/`_refresh_via_owa_piggy`/`emit_error`/`print` to a non-redirected stderr; the `run()` `try/finally` restores stderr on every exit path; `_loop`'s `except Exception` keeps non-`OwaError` from escaping into the dead buffer. Verify: first-mint placement (inside loop, seed-failure degrades not exits); exp-aware cache + `expires_at=None` coercion + evict-on-failure; `TokenInfo.scopes` from `scopes_in_token`; `_tui_get`/`_fetch_page` surface headers + **case-insensitive** continuation lookup; pagination across all three shapes; opaque reachable via `raw=True`; **agent guard closed against `--profile`** (graph **and** mail) with no `modes.py` regression for other tools; `next_path` for ARM/devops; `format_pretty` strictly graph-gated; per-tier `o`/`e` behavior; `_ensure_token` updates `state.api_base/scopes`.
- **Gate:** zero high/medium findings, else loop back to the owning agent before release.

---

## Open decisions (defaults chosen; override if needed)

1. **Nav model:** v1 ships **single list + detail pane** only; Miller columns out of scope. _(Locked — lowest-risk, reuses mail layout.)_
2. **Step 9 (FOCI client-identity selector):** **deferred / out of this release.** Requires PREREQUISITE owa-piggy changes (`owa-piggy token --client <id> [--origin <url>]` + kwargs through `owa_core.auth.get_token`); option (a) — mutating `os.environ['OWA_CLIENT_ID']` — is **forbidden** (process-global, corrupts owa-piggy's `(tenant,client_id,scope)` AT cache + RT rotation). Only 2 of ~33 FOCI clients have a known Origin (`oauth.py:KNOWN_CLIENT_ORIGINS`). **⚠ The one decision with real cost (two-repo coordinated change) — explicit go/no-go.**
3. **Bookmark privacy:** acceptable as-is — config `0600`, only `(audience,path,label)` persisted (never bodies). Paths can embed sensitive ids (vault names, drive ids, OIDs); revisit redaction only if needed.
4. **Re-fetch key:** **locked to lowercase `r`** — conventional reload; a GET-only explorer has no read/unread state (no mail-style `r` collision). All references use `r`.
5. **owa-piggy version pin for the sync test:** cite the current owa-piggy (0.7.x) in the `_KNOWN_PIGGY_AUDIENCES` snapshot comment (required, not prose); optional CI assert that installed owa-piggy ≥ that version so the literal can't silently rot.
6. **`owa-graph hosts` / endpoints.office.com catalog:** out of v1 (not on critical path).
7. **Profile selection:** **fixed for the session** (parity with mail TUI), resolved at start from `--profile`/config/`OWA_PROFILE`. The header shows active profile + tenant for diagnosability; an in-TUI profile switcher is deferred.
8. **`--beta` (v1.0/beta toggle):** **v1.0 only.** The prefix-index + scope annotation are built from `all_paths('v1.0')`, so beta paths would get no completion/annotation anyway; a beta toggle would need a second `all_paths('beta')` index — deferred.
9. **Mint cancellation:** accepted that a hung owa-piggy mint freezes the TUI for up to the `subprocess.run(timeout=60)` ceiling with no in-flight cancel (no async/threaded mint in v1). The timeout surfaces as `subprocess.TimeoutExpired → AuthExpiredError`, caught by `_ensure_token`; `curses.wrapper` restores the terminal on any eventual escape, so a freeze can't corrupt the screen.

## Notes

- **Reusable surfaces:** `auth.get_token_for_config` (use inside the loop — carries `expires_at`/`scope`; `setup_auth` discards them); `api.build_url`/`build_query`; `paths.all_paths`; `scopes.required_scopes` + `owa_core.jwt` (`scopes_in_token`, new `tenant_id`); `emit.render_curl/render_az`; `format.format_pretty` (graph-gated); `resources.GROUP_DESCRIPTIONS`. **Do NOT reuse** `api.api_request`/`api.paginate` from the loop (curses-unsafe / wrong paging), and **do NOT import** `owa_mail.tui_menu` (mail-coupled).
- **FOCI mechanics (verified):** owa-piggy `oauth.exchange_token` — `grant_type=refresh_token`, fixed client `9199bf20` (override `OWA_CLIENT_ID` + `KNOWN_CLIENT_ORIGINS`), scope `<resource>/.default`; `token_flow.exchange_fresh` gates RT shape (`1.`/`0.` prefix) and rotates the RT; `--json` mint never prompts. See memory `foci-reference-sources`, `owa-piggy-token-scope-limits`.
- **Constraints:** stdlib-only (curses/webbrowser/textwrap/binascii/io/json/time — all import on darwin); refuse under `--agent`/pipe; v1 read-only (GET + drill + hop), no mutations.
- **Self-review provenance:** round 1 — 62-agent `plan-self-review` workflow (54 findings → 49 confirmed → 22 deduped closures). Round 2 — 5 parallel reviewers (internal-consistency, code-fidelity, design-gap, orchestration, completeness): fixed the `_fetch_page` header-access contradiction, case-insensitive continuation header, `TokenInfo.scopes` source, `expires_at=None` coercion, first-mint/`curses.wrapper` lifecycle + seed-failure degradation, stderr-teardown owner + non-`OwaError` containment, `MANIFEST.in`→pyproject package-data, unowned `conftest`/`FakeScreen`, output-mode-flag rejection, schema alias, atomic-guard co-requisite (`modes.py`), mail-side regression gate, per-tier `o`/`e`/`/` behavior, `D` overlay scroll spec, profile/tenant header, and the beta/cancellation/profile open decisions.
