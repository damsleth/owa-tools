# owa-mail TUI overhaul: full-width, reading pane, search fix, esc menu + settings

> **Status: DONE** — shipped in `23b5f21` (2026-06-01),
> `feat(mail): full-width tui with reading pane, esc menu, and settings`.
> All six unit modules landed (`tui_dates.py`, `tui_layout.py`, `tui_sort.py`,
> `tui_settings.py`, `tui_menu.py`) plus the `tui.py` integration and the
> `messages.py` search-400 fix. See [DONE.md](DONE.md).
>
> Follow-up TUI ideas split off into `.plans/TODO.md`: reset-settings-to-default,
> in-TUI profile switch, and an "all inboxes" cross-profile view.

_Created 2026-06-01 · refined into a workflow-executable spec_

## Goal

Overhaul the owa-mail curses TUI in one coordinated pass:

1. **Full-width layout** — flex the list columns to fill the terminal (today they top out
   at a fixed ~87 chars and look half-empty on wide terminals).
2. **Reading pane** — show the selected message beside/below the list; placement
   `off | right | bottom`, default `right`; split ratio configurable.
3. **Search fix** — eliminate the HTTP 400 returned by TUI search.
4. **esc overlay menu** — teaminal-style: `esc` opens a centered menu (Resume / Settings /
   Help / Quit); `q` still quits instantly. A Settings submenu exposes persisted config.

Reference look (teaminal): centered logo + version/repo line, a `>`-cursor vertical menu
list, footer hint `↑/↓ navigate · enter select · esc back`.

## Locked product decisions (2026-06-01)

- **Keys**: `esc` opens/closes the overlay menu; `q` quits instantly (power-user shortcut);
  a Resume entry also closes the menu. (Previously esc/q both quit.)
- **Split ratio**: a Settings option — list/pane = `40/60 | 50/50 | 60/40`. Default `50/50`.
  When pane is `off`, the list flexes to the full terminal width.
- **Sort options** (all client-side): `date_desc` (newest, current default), `date_asc`,
  `sender` (A–Z by `from`), `subject` (A–Z), `unread_first` (unread above read, date desc
  within each group).
- **Date formats**: `iso8601` (`2026-05-11`), `ddmm` (`11.05`), `ddmm_hhmm` (`11.05 09:30`),
  `custom` (user-entered strftime string, validated).
- **Outcome**: agents implement + test each unit; a serial agent integrates into `tui.py`;
  I verify (full pytest + ruff) and leave a working branch to review.

---

## Grounding — current code (verified)

- **Framework**: Python stdlib `curses`, no external TUI deps. Entry `owa_mail/tui.py:run()`
  (`tui.py:344`), called from `cli.py:cmd_tui()` (`cli.py:939`).
- **State**: `_State` plain container (`tui.py:159`): `messages, folder, search, selected,
  top, mode, reader, reader_top, status`. Two modes: `'list'` / `'reader'`.
- **Event loop**: `_loop()` (`tui.py:282`) — `stdscr.getch()` then dispatch. esc(27)/q quit
  in list mode (`tui.py:296`); esc/q/left return to list in reader (`tui.py:322`).
- **Render**: full redraw each iteration. `_draw_list()` (`tui.py:174`), `_draw_reader()`
  (`tui.py:207`). Width via `stdscr.getmaxyx()[1]`, never hardcoded.
- **"Half width" cause**: `list_row()` (`tui.py:40-55`) builds fixed columns — `sender`
  padded/truncated to **24** (`tui.py:52`), `subject` truncated to **40** (`tui.py:53`) —
  so content stops ~87 chars regardless of terminal width. Fix = flex columns, not a cap.
- **Message model** (flattened dict, `messages.py:normalize_message` 154-183): keys incl.
  `id, received` (ISO), `from, to, subject, preview, is_read, has_attachments, flag,
  web_link, body, body_type, internet_headers`.
- **Date display**: `_date_part`/`_time_part` → `owa_core/format.py:date_part` (23) &
  `time_part` (28): naive ISO string splitting.
- **Search 400 — root cause (high confidence)**: `messages.py:build_list_query` (40-75)
  sets `$orderby = 'ReceivedDateTime desc'` (line 55) when there's no sender/subject filter,
  then for a search sets `$search="..."` and returns **with `$orderby` still present**
  (lines 58-59). Outlook/Graph reject `$search` + `$orderby` together → **HTTP 400**.
  Fix: drop `$orderby` whenever `$search` is set; `_fetch_list` already sorts client-side
  (`tui.py:95`), so ordering is preserved.
- **Sorting today**: server `$orderby` when unfiltered; client-side newest-first in
  `_fetch_list` (`tui.py:95`) and `read` (`cli.py:436`). Only key is `received`.
- **Config**: `~/.config/owa-mail/config` (XDG), shell-sourceable `KEY="VALUE"`, mode 0600,
  atomic write. `owa_mail/config.py`: `CONFIG_PATH` (15) + `ALLOWED_KEYS` tuple (19) wrapping
  `owa_core.config` primitives. Today only `owa_piggy_profile`, `debug`.
- **Tests**: pytest under `src/tests/mail/`. `test_tui.py` (130 lines) covers **pure helpers**
  (`list_row`, `reader_lines`) + thin network wrappers + the interactive guard; the curses
  loop is intentionally not unit-tested. NOTE: `test_tui.py` asserts `row[17] == "*"` — a
  fixed-column-position assertion that **will change** once columns flex (integration
  agent must update it).

---

## Architecture for parallel execution

Almost all logic lives in one 357-line file (`tui.py`), so parallel agents must **not**
edit it concurrently. Strategy: extract each new concern into its **own new pure module**
with its **own new test file** (disjoint import graphs → no collisions, no worktrees
needed), then one **serial integration agent** rewrites `tui.py` to consume them.

New modules (all pure, no curses):

| Module | Responsibility |
|---|---|
| `owa_mail/tui_dates.py` | Format an ISO datetime per a date-format setting |
| `owa_mail/tui_layout.py` | Compute list/pane regions from (width,height,placement,ratio); render a width-filling list row; wrap body for the pane |
| `owa_mail/tui_sort.py` | `sort_messages(messages, sort_by)` — pure, stable |
| `owa_mail/tui_settings.py` | Settings dataclass: defaults, validation, option enums, cycle-next, load/save (+ extend `config.py` ALLOWED_KEYS) |
| `owa_mail/tui_menu.py` | Overlay menu model: menu tree, cursor nav state machine, pure render-to-lines (centered box + footer) |

`messages.py` (search fix) is touched only by the search agent. `config.py` is touched only
by the settings agent. `tui.py` + `test_tui.py` are touched only by the integration agent.

**Concurrency rule for fan-out agents**: each runs **only its own new test file**
(`pytest src/tests/mail/test_<module>.py -q`), never the whole suite — another agent's
half-written file on disk must not break an unrelated agent's collection. Whole-suite +
ruff runs in the serial verify stage.

---

## Unit specs (each = one fan-out agent: implement module + tests, run own tests)

### U1 — Search 400 fix  (`messages.py`, `test_messages*.py`)
- In `build_list_query`, when `search` is truthy: remove `$orderby` from `params` before
  returning (`params.pop('$orderby', None)`), then set `$search=f'"{search}"'`.
- Keep the existing early return. Add a code comment: `$search` and `$orderby` are mutually
  exclusive in Outlook/Graph (400 otherwise).
- Tests: (a) `build_list_query(search='budget')` → has `$search`, **no** `$orderby`;
  (b) unfiltered (no search/sender/subject) still has `$orderby ReceivedDateTime desc`;
  (c) sender/subject path unchanged.

### U2 — Date formatting  (`tui_dates.py`, `test_tui_dates.py`)
- `format_received(iso: str, fmt: str, custom: str = "") -> str`. `fmt ∈
  {iso8601, ddmm, ddmm_hhmm, custom}`.
  - `iso8601` → `YYYY-MM-DD`; `ddmm` → `DD.MM`; `ddmm_hhmm` → `DD.MM HH:MM`;
    `custom` → `datetime.strftime(custom)`.
- `validate_custom_format(s: str) -> bool` — true iff `s` is a non-empty, safe strftime
  string (format a fixed sample datetime; false on exception/empty).
- Parse ISO defensively (handle trailing `Z`, missing time). Empty input → `''`.
  No dependence on local timezone beyond what the stored ISO already encodes.
- Tests: each format on `2026-05-11T09:30:00Z`; empty string; malformed string;
  `validate_custom_format` true/false cases.

### U3 — Layout / regions  (`tui_layout.py`, `test_tui_layout.py`)
- `regions(width, height, placement, ratio) -> Regions` describing list rect and pane rect
  (x, y, w, h) for `placement ∈ {off, right, bottom}` and `ratio ∈ {40,50,60}` (= list %).
  `off` → list = full width, no pane. `right` → side-by-side, list width = `ratio%`,
  with a 1-col divider. `bottom` → stacked, list height = `ratio%`, 1-row divider.
- `list_row(msg, width, *, date_fmt, custom_fmt) -> str` — flex version: fixed marker
  columns (date/time per date_fmt, `*`/`!`/`@` flags), then **sender and subject expand to
  fill remaining width** (e.g. sender ≈ 30%, subject takes the rest), final-truncate to
  width. Must still satisfy `len(row) <= width`.
- `wrap_body(text, width) -> list[str]` for the pane (reuse/share logic with existing
  `reader_lines` semantics incl. footnote links; integration agent reconciles).
- Tests: regions math for each placement/ratio (widths sum correctly, divider accounted,
  degenerate tiny terminals don't crash/go negative); `list_row` fills width and fits;
  narrow-width truncation; flag columns at expected offsets.

### U4 — Sorting  (`tui_sort.py`, `test_tui_sort.py`)
- `sort_messages(messages, sort_by) -> list` (returns a new list; stable). `sort_by ∈
  {date_desc, date_asc, sender, subject, unread_first}`.
  - `date_*` by `received`; `sender` by `from` casefold; `subject` by `subject` casefold;
    `unread_first` → not `is_read` first, then `received` desc within group.
- Missing/None fields sort last (or as empty string) — never raise.
- Tests: each key on a small fixture; stability; missing-field safety.

### U5 — Settings model + persistence  (`tui_settings.py`, `config.py`, `test_tui_settings.py`)
- `Settings` dataclass: `reading_pane: str = 'right'`, `split_ratio: int = 50`,
  `sort_by: str = 'date_desc'`, `date_format: str = 'iso8601'`, `date_custom: str = ''`.
- Per field: an ordered tuple of allowed values + `cycle(field) -> Settings` returning the
  next value (wraps). `date_custom` is free text (entered via the menu's text prompt).
- `from_config(config) -> Settings` / `to_config_dict(settings) -> dict[str,str]` mapping to
  shell-safe `KEY="VALUE"` entries. Validate on load; unknown/invalid → default.
- Extend `owa_mail/config.py` `ALLOWED_KEYS` with: `tui_reading_pane`, `tui_split_ratio`,
  `tui_sort_by`, `tui_date_format`, `tui_date_custom`.
- Tests: defaults; round-trip `from_config(to_config_dict(s)) == s`; cycle wraps for each
  enum; invalid stored value falls back to default; `config.py` accepts the new keys.

### U6 — Overlay menu model  (`tui_menu.py`, `test_tui_menu.py`)
- A pure state machine, no curses. `Menu` holds: current screen (`top` | `settings`),
  cursor index, and the item lists.
  - Top items: `Resume, Settings, Help, Quit`.
  - Settings items: one row per setting, each rendering `label: <current value>`
    (e.g. `Reading pane: right`). Selecting cycles the value (calls into U5) — except
    `date_format=custom` / `date_custom`, which signal the host to open a text prompt.
- Methods: `move(delta)`, `select() -> Action` where `Action ∈ {resume, quit, open_settings,
  back, cycle(field), edit_custom, help, none}`, `back()`.
- `render(width, height, settings) -> list[str]` — centered box lines: title/logo block,
  the `>`-cursor item list, and footer `↑/↓ navigate · enter select · esc back`. Pure;
  integration agent blits these lines via `_safe_addstr`.
- Tests: navigation wraps/clamps; `select()` returns correct Action per item/screen;
  Settings rows reflect current `Settings`; `render` produces centered lines within
  width/height and includes the footer.

---

## Integration spec (serial — single agent, after U1–U6 land)

Agent edits **`tui.py`** + **`test_tui.py`** only. Imports the six modules.

- **State**: extend `_State` with `settings: Settings`, `menu_open: bool`,
  `menu: Menu`. Load settings via `tui_settings.from_config(config)` in `run()`.
- **Keys** (`_loop`):
  - List mode: `esc` → open menu (`menu_open=True`); `q` → quit; all other keys unchanged.
  - When `menu_open`: route `↑/↓/j/k` → `menu.move`, `enter` → `menu.select()` and act on the
    Action (resume→close; quit→return; open_settings/back→navigate; cycle→update settings &
    persist; edit_custom→`_prompt` for a strftime string, validate via U2, persist; help→
    help screen), `esc` → `menu.back()` or close at top level.
  - Persist settings (`tui_settings.to_config_dict` → `owa_mail.config.write`) whenever a
    value changes.
- **Render**:
  - Compute `regions(...)` from terminal size + `settings.reading_pane/split_ratio`.
  - `_draw_list` renders into the list rect using the flex `tui_layout.list_row` with
    `settings.date_format/date_custom`; apply `tui_sort.sort_messages` to ordering
    (replace the hardcoded newest-first where appropriate, or sort in `_fetch_list`).
  - New `_draw_reading_pane` renders the selected message body (via `wrap_body`) into the
    pane rect when placement ≠ `off`; draw the 1-col/1-row divider. The existing full-screen
    `reader` mode stays as the `enter`-to-focus full view.
  - When `menu_open`, blit `menu.render(...)` centered as an overlay (drawn last).
- **Tests** (`test_tui.py`): update the fixed-position assertion (`row[17]`) for flex
  columns; add a test that list_row reflects the chosen date_format; keep curses loop
  untested per existing convention. Pure menu/settings/layout behavior is covered by U2–U6.

## Verification stage (after integration)

- One agent runs the **whole suite** `pytest src/tests/mail/ -q` and `ruff check src/` (the
  repo uses ruff; sort imports / I001). Report failures with output. Iterate via the
  integration agent if red.
- Manual curses smoke can't run headless in the workflow — I'll note it for you to eyeball:
  `owa-mail tui` → resize terminal (full width), `esc` (menu), Settings → cycle reading
  pane/ratio/sort/date format, `/` search (no 400), `q` quits.

## Workflow DAG (orchestration)

```
phase Fan-out (parallel, disjoint files, each runs only its own test file):
  U1 search-fix · U2 dates · U3 layout · U4 sort · U5 settings · U6 menu
        │  (barrier: all six must land before integration touches tui.py)
phase Integrate (serial, 1 agent): wire U1–U6 into tui.py + update test_tui.py
        │
phase Verify (1 agent): full pytest + ruff; loop back to Integrate on failure
```

- Barrier before integration is genuine (integration imports all six). Within fan-out,
  no cross-item dependency → plain `parallel()`.
- Each agent gets: the relevant grounding excerpt above, its unit spec, the
  "own-test-file-only" rule, and the repo test/ruff conventions.
- Schema per fan-out agent: `{module, files_created[], files_edited[], tests_added[],
  test_command, test_passed: bool, notes}` so the orchestrator can gate the barrier on
  `test_passed`.

## Open risks / notes

- `wrap_body` vs existing `reader_lines` (footnote-link handling, `tui.py`): integration
  agent must reconcile so the pane and the full reader view stay consistent — don't
  duplicate divergent wrapping. Prefer extracting the existing logic into `tui_layout`.
- `$search` query is still unvalidated KQL; U1 only fixes the orderby conflict. A malformed
  user query could still 400 — out of scope unless we add input sanitization later.
- Confirm ruff import-sort (I001) passes on every new module (repo enforces it — see recent
  `style(doctor)` commit).
