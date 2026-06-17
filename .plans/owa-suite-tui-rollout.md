# owa suite TUI rollout (v1)

_Created 2026-06-12 · architecture reconciled 2026-06-15: this is the **master TUI
plan**. `owa_core/tui_kit/` (Step 0) is the shared foundation; every per-tool TUI —
including the owa-graph FOCI explorer — is an adapter on top. See
[owa-graph-explorer-tui.md](owa-graph-explorer-tui.md) for the owa-graph adapter,
now re-cast as the flagship/most-complex consumer of `tui_kit` rather than a
standalone mail-pattern copy._

## Goal

Give every owa-* consumer tool that lacks one a simple, intuitive, **dependency-free
curses TUI**, sharing a common look-and-feel so the whole suite feels like one product.
The default `<tool> tui` interaction lists (or affords CRUD on) that tool's canonical
item type. v1 is deliberately modest — list + detail + search + a couple of safe
actions — not a full client.

**Reference implementation:** `owa-mail` already ships this exact shape
(`src/owa_mail/tui*.py`, ~1700 LoC, stdlib `curses`/`webbrowser`/`textwrap`). The mail
TUI's structure (pure layout helpers + `_loop()` event loop + esc-menu overlay +
persisted view settings) is the template every other tool follows.

## Scope

**owa-mail** — already done, used as the pattern (no work).

**v1 in-scope tools** (one `tui` subcommand each):

| Tool        | Canonical item / default view                                                                 |
|-------------|-----------------------------------------------------------------------------------------------|
| owa-cal     | Agenda — list of events (today/week), drill to event detail; respond/accept as actions        |
| owa-people  | Searchable directory list → person detail card                                                |
| owa-drive   | `lf`-like folder/file hierarchy navigation                                                     |
| owa-todo    | Two-pane: lists sidebar + task list; toggle done, create/edit                                  |
| owa-planner | Plan → bucket → task drill (bucket-grouped task view inside a plan)                             |
| owa-ado     | Work-items list (assigned-to-me / current sprint), filterable, drill to detail                 |
| owa-teams   | Chats list (1:1 + group) → read message thread                                                 |
| owa-sched   | Free/busy availability grid (attendees × time slots)                                           |
| owa-graph   | **Multi-audience FOCI explorer** — navigate/drill any FOCI audience owa-piggy can mint (flagship adapter; supersedes the old "request browser" framing). See owa-graph-explorer-tui.md |
| owa-doctor  | Live health dashboard — profiles × audiences grid with pass/fail, refresh in place             |
| owa-sites   | `lf`-like SharePoint browser (see decision below)                                              |

**Deferred from v1:**
- **owa-vids** — acts on a pasted URL, not a list; no natural TUI. Revisit if a
  download queue/progress view becomes worthwhile.

## Key decisions (from user)

- **owa-sites** = unified `lf`-like browser, *not* three separate modes:
  - Top level = **sites** (list/search).
  - Enter a site → its **lists + document libraries** together, with a toggle to
    show/hide hidden lists/libraries (mirrors `lf`'s hidden-file toggle).
  - Enter a library/list → drill down to individual **documents / list items**.
  - `/` or `cmd+f` is the class-wide search action at every level.
- **owa-ado** default = work-items list (not sprint board, not project-picker-first).
- **owa-teams** default = chats list reader (not the teams→channels drill).
- **owa-planner** = plan→bucket→task drill (not a flat my-tasks list).
- **owa-sched** = availability grid (not find-time picker).
- `/` (and ideally `cmd+f` where the terminal delivers it) is the search keybinding
  across **all** tools, matching the owa-sites decision — keep it consistent.

## Architecture

The central v1 question: **share scaffolding, or copy the mail pattern per tool?**

**Decision: extract a small shared curses kit into `owa_core` first, then build each
tool's TUI as a thin adapter on top.** This is what makes the suite feel coherent
(the user's "common thread"), avoids 11× copies of the event loop, and keeps each
tool's TUI to roughly an item-adapter + draw-detail function.

### Step 0 — `owa_core/tui_kit/` (shared, dependency-free)

Factor the reusable parts out of `owa_mail/tui*.py` into `owa_core`:
- **`tui_kit/app.py`** — the curses event loop: a generic list/detail browser
  parameterized by callbacks (`fetch_items`, `render_row`, `render_detail`,
  `actions`, `on_search`). Handles selection movement, scrolling, resize, redraw.
- **`tui_kit/layout.py`** — pure region/wrap/truncate helpers (lift from
  `tui_layout.py`; keep them pure + unit-testable).
- **`tui_kit/menu.py`** — the esc-overlay menu (from `tui_menu.py`).
- **`tui_kit/settings.py`** — view-settings cycle + config persistence
  (from `tui_settings.py`).
- **`tui_kit/keys.py`** — one keybinding table so `/`, `j/k`, arrows, `enter`,
  `esc`, `q`, `r` (refresh) mean the same thing everywhere. Standardize the
  `/`-search action here.
- Reuse existing `owa_core/tty.py` (`is_interactive`) for the no-TTY guard.

Then **refactor owa-mail to consume `tui_kit`** (proves the abstraction; keep its
existing tests green). Mail keeps its mail-specific bits (reader pane, read/unread).

### Per-tool work (repeat for each in-scope tool)

1. Add `cmd_tui(args, config, access_token, api_base)` in `<tool>/cli.py`, mirroring
   `owa_mail`'s: guard with `tty_mod.is_interactive(...)`, raise `UsageError` under
   `--agent`/pipe, then call `tui.run(...)`.
2. Register the subcommand: add to the dispatch dict, the help text, and the
   `schema_mod.command('tui', ..., interactive=True)` registration, and add `'tui'`
   to `interactive_commands=(...)`.
3. Write `<tool>/tui.py` — a thin adapter providing the `tui_kit.app` callbacks:
   `fetch_items` (reuse the tool's existing API/data functions), `render_row`,
   `render_detail`, and a small `actions` set (the safe subset of the tool's CRUD).
4. Tests under `src/tests/<tool>/test_tui*.py` — cover the **pure** helpers
   (row formatting, layout, sort/filter, adapter mapping). Curses loop stays
   untested (as in mail). Mind the **90% coverage gate** — pure helpers must be
   well-covered to clear it.

### CRUD scope per tool (v1 = read + safe actions; keep mutations behind confirm)

- **owa-cal** — read agenda + event detail; action: respond (accept/decline/tentative).
  Create/update/delete deferred unless trivial.
- **owa-people** — read-only (search + detail card).
- **owa-drive** — navigate + open/download; `rm`/`put` deferred (or behind confirm).
- **owa-todo** — list/tasks read, toggle done, create task (the canonical CRUD example).
- **owa-planner** — read drill; toggle task complete.
- **owa-ado** — read work-items + detail; state change (e.g. → Active/Done) optional.
- **owa-teams** — read chats + thread (read-only v1; no send).
- **owa-sched** — read-only availability grid.
- **owa-graph** — read-only request runner (GET-first; guard mutating verbs behind confirm).
- **owa-doctor** — read-only dashboard; `r` re-runs checks.
- **owa-sites** — navigate + open/download; read-only v1.

## Parallelization & workflow execution

This plan is a **barrier-then-fan-out** workflow:

- **Step 0 (`tui_kit` extraction + mail refactor) is a hard barrier.** Nothing else
  can start until the kit's callback contract (`fetch_items`/`render_row`/
  `render_detail`/`actions`/`on_search`) is frozen and mail is green on top of it.
  Single agent (OPUS — the abstraction shape is the whole bet). The contract it
  freezes is the shared symbol every downstream adapter imports, so it must be
  right before fan-out.
- **After Step 0, each tool's adapter is region-disjoint** (`src/owa_<tool>/tui.py`
  + `src/owa_<tool>/cli.py` dispatch + `src/tests/<tool>/`). No two adapters share a
  file → they fan out cleanly. Use `pipeline(tools, build_adapter, verify_coverage)`
  so each tool verifies its 90% gate as soon as it's built rather than at a barrier.
- **Sequencing constraints inside the fan-out:**
  - **owa-todo first, alone** (or as a tiny pilot batch) — it's the canonical CRUD
    adapter and validates the kit's `actions` shape before 10 others copy it. Treat
    its completion as a soft gate.
  - **owa-cal TUI is blocked on the in-flight periods work (#9 / ergonomic-semantic-period-params)** — both edit `owa_cal/cli.py`. Build cal's adapter only after #9 lands, or accept a merge.
  - **drive → sites are sequential** (sites generalizes drive's `lf` model).
  - **owa-graph is the flagship adapter** — it carries its own deep plan
    (owa-graph-explorer-tui.md) with a curses-safe auth/cache core and per-audience
    nav engine that `tui_kit` does NOT absorb. Schedule it late and give it OPUS for
    its two correctness cores. It is itself a sub-workflow.
- Realistic fan-out width ~3–4 concurrent adapters (the per-tool coverage gate +
  shared-kit churn make more than that risky to merge).

## Steps

- [x] Step 0 (2026-06-16): extracted `owa_core/tui_kit/` (`app`/`layout`/`menu`/`settings`/`keys`/`screen`) from owa-mail; refactored owa-mail onto it (tui_layout re-exports geometry; tui_settings delegates to the engine; tui_menu subclasses the generic Menu; tui.py aliases the kit's `_safe_addstr`/`_prompt`/`_pad`/`_truncate`/`_init_colors`) — mail shrank ~558 lines. **Callback contract frozen** in `tui_kit/app.py` (`fetch_items`/`render_row`/`render_detail`/`on_search`/`on_drill`/`on_back`/`on_refresh`/`on_menu_action`/`actions`); fetch is curses-safe (sets `state.items`/`state.status`, never raises) and runs inside the loop on `state.dirty`, so an adapter can show a "minting…" frame first. Mail tests green; owa_core gate 96.42% (≥95), combined 90.39% (≥89). Kit tests under `src/tests/core/tui_kit/`.
- [ ] Step 0.1 — **tui_kit: pass `stdscr` to action callbacks** (additive; see the kit-enhancement finding below). Land before the wide fan-out so new adapters don't reimplement the loop. Then retrofit: drop owa-cal's `_cal_loop`, make owa-graph's `a` a selectable audience overlay, add a pre-fetch redraw hook for the "minting…" frame.
- [ ] owa-todo tui — two-pane lists+tasks, toggle done, create (validates adapter shape; soft gate before wide fan-out)
- [ ] owa-people tui — searchable directory list → detail card (read-only quick win)
- [x] owa-cal tui (2026-06-17) — agenda list + event detail + respond action (accept/decline/tentative behind a confirm prompt), `o` open in browser, `/` search, `--day-range` horizon. New `owa_cal/{tui,tui_settings,tui_menu}.py` + `cmd_tui` (refuses non-interactive AND under `--agent` via `interactive_commands`; rejected on webcal sources); docs section in `docs/cal.md`. ≈55 cal tests; `owa_cal/tui.py` 75% (curses loop pragma'd). First consumer of `tui_kit.app` alongside owa-graph.
- [ ] owa-drive tui — `lf`-like folder/file navigation
- [ ] owa-sites tui — `lf`-like sites→lists/libraries(+hidden toggle)→items/docs, `/` search (after drive)
- [ ] owa-ado tui — work-items list (assigned/sprint) → detail
- [ ] owa-planner tui — plan→bucket→task drill, toggle complete
- [ ] owa-teams tui — chats list → message thread (read-only)
- [ ] owa-sched tui — free/busy availability grid (attendees × time slots)
- [~] owa-graph tui — **flagship FOCI explorer adapter** on tui_kit (own sub-plan: owa-graph-explorer-tui.md; OPUS cores). Phase 0/1/2 DONE (2026-06-16/17): audiences+seeds, nav engine, auth/cache, and the curses front-end on `tui_kit.app`. **Remaining: Phase 3 (CLI wiring — `cmd_tui`/schema/`modes.py` `--profile` guard) + Phase 4 (docs/version/R1).**

**Kit-enhancement finding (surfaced by both first adapters):** `tui_kit.app`'s `actions[key](state)` contract passes no `stdscr`, so a tool action that must draw a prompt or overlay can't. Both adapters worked around it: owa-cal copied the kit `_loop` into a local `_cal_loop` that drains a `state._pending_respond` sentinel with `stdscr` in hand; owa-graph fell back to a round-robin `a` instead of a selectable audience overlay. **Proposed additive kit change (does not break the frozen contract): pass `stdscr` to action callbacks (or expose a `state`-level prompt/overlay hook) so adapters stop reimplementing the loop.** Also added in this pass: `tui_kit.screen.silence_os_fds()` (shared fd-silencer for browser/clipboard launches).
- [ ] owa-doctor tui — live health dashboard (profiles × audiences), `r` refresh
- [ ] (deferred) owa-vids — no v1 TUI; revisit download-queue view later

## Notes

- **Build order rationale:** Step 0 de-risks everything; owa-todo proves the adapter;
  drive→sites share the `lf` model (build drive, generalize for sites); graph/doctor
  (non-list browsers) last. Each tool is independently shippable after Step 0 — release
  incrementally (CHANGELOG + version bump per the release-gotchas memory).
- **`cmd+f`:** terminals rarely deliver `cmd+f` to curses; treat `/` as the guaranteed
  search key and accept `cmd+f` only where the terminal forwards it. Don't block v1 on it.
- **Coverage gate (~0 slack, 90%):** keep all logic in pure, tested helpers; the curses
  `_loop` is the only untested surface — same discipline as owa-mail.
- **No-TTY contract:** every `tui` must refuse under `--agent`/pipe (suite captures stdout
  as JSON) — reuse `owa_core.tty.is_interactive`.
- **owa-graph mutations:** decide whether the v1 request browser is GET-only or allows
  mutating verbs behind a confirm prompt — leaning GET-first for safety.
- **No new API calls:** reuse each tool's existing API layer for `fetch_items`; the TUI
  should add no Graph/REST calls beyond what the CLI already does.
- **Umbrella discoverability:** consider `owa tui` later listing available per-tool TUIs —
  out of v1 scope.
