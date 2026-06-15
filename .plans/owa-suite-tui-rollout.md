# owa suite TUI rollout (v1)

_Created 2026-06-12_

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
| owa-graph   | Request/response browser — pick method+path, scrollable/foldable JSON response                 |
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

## Steps

- [ ] Step 0: extract `owa_core/tui_kit/` (app/layout/menu/settings/keys) from owa-mail; refactor owa-mail onto it; keep mail tests green
- [ ] owa-todo tui — two-pane lists+tasks, toggle done, create (validates adapter shape)
- [ ] owa-people tui — searchable directory list → detail card (read-only quick win)
- [ ] owa-cal tui — agenda list + event detail + respond action
- [ ] owa-drive tui — `lf`-like folder/file navigation
- [ ] owa-sites tui — `lf`-like sites→lists/libraries(+hidden toggle)→items/docs, `/` search
- [ ] owa-ado tui — work-items list (assigned/sprint) → detail
- [ ] owa-planner tui — plan→bucket→task drill, toggle complete
- [ ] owa-teams tui — chats list → message thread (read-only)
- [ ] owa-sched tui — free/busy availability grid (attendees × time slots)
- [ ] owa-graph tui — request/response browser, foldable JSON (GET-first)
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
