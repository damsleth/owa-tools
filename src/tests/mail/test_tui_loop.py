"""Loop + draw coverage for the owa-mail TUI via a fake curses screen.

test_tui.py covers the pure helpers; this module drives the curses-bound
surface — _loop's key dispatch (the focus model, menu navigation, reading-pane
scrolling), the draw_* functions, and the action handlers — through a
FakeScreen so they run without a real terminal.
"""
import pytest

from owa_mail import tui
from owa_mail.tui_settings import Settings


class FakeScreen:
    """Minimal stand-in for a curses window/stdscr.

    Records addstr calls so tests can assert on rendered text, and replays a
    scripted list of getch() keypresses (falling back to 'q' so a loop always
    terminates)."""

    def __init__(self, h=24, w=100, keys=None):
        self._h, self._w = h, w
        self._keys = list(keys or [])
        self.drawn = []

    def getmaxyx(self):
        return (self._h, self._w)

    def erase(self):
        self.drawn.clear()

    def addstr(self, y, x, text, attr=0):
        self.drawn.append((y, x, text, attr))

    def refresh(self):
        pass

    def keypad(self, flag):
        pass

    def getch(self):
        return self._keys.pop(0) if self._keys else ord('q')

    def getstr(self, y, x, n=0):
        return b''

    def text(self):
        return "\n".join(t for _, _, t, _ in self.drawn)


@pytest.fixture(autouse=True)
def _no_terminal(monkeypatch):
    """The cursor/echo calls need a real terminal; neutralise them."""
    monkeypatch.setattr(tui.curses, 'curs_set', lambda *a: None)
    monkeypatch.setattr(tui.curses, 'echo', lambda *a: None)
    monkeypatch.setattr(tui.curses, 'noecho', lambda *a: None)


def _msgs(n=6):
    return [
        {"id": f"m{i}", "received": f"2026-05-{10 + i:02d}T09:00:00Z",
         "from": f"a{i}@x.com", "subject": f"Subject {i}", "is_read": i % 2 == 0,
         "web_link": "https://example.test/m"}
        for i in range(n)
    ]


def _state(reading_pane='off', n=6):
    return tui._State(_msgs(n), "Inbox", Settings(reading_pane=reading_pane))


# --- loop: list focus navigation -------------------------------------------

def test_loop_list_navigation_quits():
    st = _state('off')
    tui._loop(FakeScreen(keys=[ord('j'), ord('j'), ord('k'), ord('q')]),
              st, "base", "tok", False, {})
    assert st.selected == 1  # down twice, up once


def test_loop_G_jumps_to_bottom():
    st = _state('off')
    tui._loop(FakeScreen(keys=[ord('G'), ord('q')]), st, "base", "tok", False, {})
    assert st.selected == 5


def test_loop_half_page_down_clamps():
    st = _state('off')
    tui._loop(FakeScreen(h=24, keys=[ord('d'), ord('q')]), st, "base", "tok", False, {})
    assert st.selected == 5  # half of (24-2) overshoots, clamped to last


# --- loop: reading-pane focus model ----------------------------------------

def _stub_body(monkeypatch, lines=200):
    monkeypatch.setattr(tui, '_fetch_body', lambda *a, **k: {"id": "x", "body": "b"})
    monkeypatch.setattr(
        tui, 'format_message_pretty',
        lambda m: "\n".join(f"line{i}" for i in range(lines)),
    )


def test_loop_l_enters_pane_and_scrolls(monkeypatch):
    _stub_body(monkeypatch)
    st = _state('right')
    tui._loop(FakeScreen(keys=[ord('l'), ord('j'), ord('j'), ord('q')]),
              st, "base", "tok", False, {})
    assert st.focus == 'pane'
    assert st.pane_top == 2


def test_loop_h_returns_to_list(monkeypatch):
    _stub_body(monkeypatch)
    st = _state('right')
    tui._loop(FakeScreen(keys=[ord('l'), ord('h'), ord('q')]),
              st, "base", "tok", False, {})
    assert st.focus == 'list'


def test_loop_l_with_pane_off_opens_full_reader(monkeypatch):
    _stub_body(monkeypatch)
    st = _state('off')
    tui._loop(FakeScreen(keys=[ord('l'), ord('q'), ord('q')]),
              st, "base", "tok", False, {})
    # l with no pane opens the full reader; first q backs out, second quits.
    assert st.reader  # reader was populated


# --- loop: overlay menu -----------------------------------------------------

def test_loop_esc_opens_then_closes_menu():
    st = _state('off')
    tui._loop(FakeScreen(keys=[27, 27, ord('q')]), st, "base", "tok", False, {})
    assert st.menu_open is False


def test_loop_reader_scroll_then_back(monkeypatch):
    _stub_body(monkeypatch, lines=100)
    st = _state('off')
    tui._loop(FakeScreen(keys=[13, ord('j'), ord('j'), ord('q'), ord('q')]),
              st, "base", "tok", False, {})
    assert st.mode == 'list'  # Enter → reader, q → back to list, q → quit


# --- draw functions ---------------------------------------------------------

def test_draw_list_renders_header_and_rows():
    scr = FakeScreen()
    tui._draw_list(scr, _state('off'))
    txt = scr.text()
    assert 'owa-mail' in txt
    assert 'Subject' in txt


def test_draw_list_right_pane_shows_body(monkeypatch):
    monkeypatch.setattr(tui, 'format_message_pretty', lambda m: "BODYLINE\nsecond")
    scr = FakeScreen()
    tui._draw_list(scr, _state('right'))
    assert 'BODYLINE' in scr.text()


def test_draw_list_bottom_pane_shows_body(monkeypatch):
    monkeypatch.setattr(tui, 'format_message_pretty', lambda m: "BODYLINE")
    scr = FakeScreen()
    tui._draw_list(scr, _state('bottom'))
    assert 'BODYLINE' in scr.text()


def test_draw_reader_renders():
    st = _state('off')
    st.reader = [f"line{i}" for i in range(50)]
    st.mode = 'reader'
    scr = FakeScreen()
    tui._draw_reader(scr, st)
    assert 'reading' in scr.text()


def test_draw_menu_renders_footer():
    st = _state('off')
    st.menu_open = True
    scr = FakeScreen()
    tui._draw_menu(scr, st)
    assert 'navigate' in scr.text()


# --- action handlers --------------------------------------------------------

def test_handle_menu_action_cycle_persists(monkeypatch):
    monkeypatch.setattr(tui, '_save_config', lambda c: None)
    st = _state('off')
    cfg = {}
    before = st.settings.reading_pane
    quit_ = tui._handle_menu_action(FakeScreen(), st, 'cycle:reading_pane', cfg,
                                    "base", "tok", False)
    assert quit_ is False
    assert st.settings.reading_pane != before
    assert 'tui_reading_pane' in cfg  # written for persistence


def test_handle_menu_action_quit():
    st = _state('off')
    assert tui._handle_menu_action(FakeScreen(), st, 'quit', {}, "base", "tok", False) is True


def test_handle_menu_action_resume_closes():
    st = _state('off')
    st.menu_open = True
    tui._handle_menu_action(FakeScreen(), st, 'resume', {}, "base", "tok", False)
    assert st.menu_open is False


def test_handle_menu_action_open_settings_and_back():
    st = _state('off')
    tui._handle_menu_action(FakeScreen(), st, 'open_settings', {}, "base", "tok", False)
    assert st.menu.screen == 'settings'
    tui._handle_menu_action(FakeScreen(), st, 'back', {}, "base", "tok", False)
    assert st.menu.screen == 'top'


def test_handle_menu_action_help_closes():
    st = _state('off')
    st.menu_open = True
    tui._handle_menu_action(FakeScreen(), st, 'help', {}, "base", "tok", False)
    assert st.menu_open is False


def test_handle_menu_action_edit_custom(monkeypatch):
    monkeypatch.setattr(tui, '_prompt', lambda scr, label: '%d.%m')
    monkeypatch.setattr(tui, '_save_config', lambda c: None)
    st = _state('off')
    tui._handle_menu_action(FakeScreen(), st, 'edit_custom', {}, "base", "tok", False)
    assert st.settings.date_custom == '%d.%m'
    assert st.settings.date_format == 'custom'


def test_handle_menu_action_edit_custom_invalid(monkeypatch):
    monkeypatch.setattr(tui, '_prompt', lambda scr, label: '%Q-not-valid-%')
    monkeypatch.setattr(tui, '_validate_custom_format', lambda s: False)
    st = _state('off')
    tui._handle_menu_action(FakeScreen(), st, 'edit_custom', {}, "base", "tok", False)
    assert 'invalid' in st.status


# --- standalone actions -----------------------------------------------------

def test_open_selected_sets_reader_mode(monkeypatch):
    monkeypatch.setattr(tui, '_fetch_body', lambda *a, **k: {"id": "m5", "body": "hi"})
    monkeypatch.setattr(tui, 'format_message_pretty', lambda m: "hello\nworld")
    st = _state('off')
    tui._open_selected(FakeScreen(), st, "base", "tok", False)
    assert st.mode == 'reader'
    assert st.reader


def test_open_selected_handles_fetch_failure(monkeypatch):
    monkeypatch.setattr(tui, '_fetch_body', lambda *a, **k: None)
    st = _state('off')
    tui._open_selected(FakeScreen(), st, "base", "tok", False)
    assert st.mode == 'list'
    assert 'failed' in st.status


def test_do_search_updates_messages(monkeypatch):
    monkeypatch.setattr(tui, '_prompt', lambda scr, label: 'budget')
    monkeypatch.setattr(tui, '_fetch_list', lambda *a, **k: _msgs(3))
    st = _state('off')
    tui._do_search(FakeScreen(), st, "base", "tok", False)
    assert st.search == 'budget'
    assert len(st.messages) == 3
    assert st.focus == 'list' and st.pane_top == 0


def test_do_search_cancelled(monkeypatch):
    monkeypatch.setattr(tui, '_prompt', lambda scr, label: None)
    st = _state('off')
    tui._do_search(FakeScreen(), st, "base", "tok", False)
    assert st.search == ''  # unchanged


def test_prompt_returns_stripped_string():
    assert tui._prompt(FakeScreen(), 'search: ') == ''


def test_toggle_read_flips(monkeypatch):
    monkeypatch.setattr(tui, '_set_read', lambda *a, **k: True)
    st = _state('off')
    before = tui._sorted_messages(st)[0].get('is_read')
    tui._toggle_read(st, "base", "tok", False)
    assert tui._sorted_messages(st)[0].get('is_read') == (not before)


def test_open_browser_opens_link(monkeypatch):
    opened = {}
    monkeypatch.setattr(tui.webbrowser, 'open', lambda url: opened.setdefault('url', url))
    st = _state('off')
    tui._open_browser(st)
    assert opened['url'] == "https://example.test/m"


# --- run() entry ------------------------------------------------------------

def test_run_invokes_wrapper(monkeypatch):
    monkeypatch.setattr(tui, '_fetch_list', lambda *a, **k: _msgs(2))
    monkeypatch.setattr(tui.folders_mod, 'resolve_folder_id', lambda f: f or 'Inbox')
    called = {}
    monkeypatch.setattr(tui.curses, 'wrapper', lambda fn, *a: called.setdefault('w', True))
    assert tui.run({}, "tok", "base", folder="Inbox") == 0
    assert called['w']


def test_run_returns_1_on_fetch_failure(monkeypatch):
    monkeypatch.setattr(tui, '_fetch_list', lambda *a, **k: None)
    assert tui.run({}, "tok", "base") == 1


# --- broad key coverage per focus ------------------------------------------

def test_loop_list_misc_keys(monkeypatch):
    import curses as _c
    monkeypatch.setattr(tui, '_set_read', lambda *a, **k: True)
    monkeypatch.setattr(tui.webbrowser, 'open', lambda url: None)
    monkeypatch.setattr(tui, '_prompt', lambda scr, label: None)  # cancel search
    st = _state('off')
    keys = [_c.KEY_DOWN, _c.KEY_UP, ord(' '), _c.KEY_PPAGE, _c.KEY_NPAGE,
            ord('o'), ord('r'), ord('/'), ord('x'), ord('q')]
    tui._loop(FakeScreen(keys=keys), st, "base", "tok", False, {})


def test_loop_pane_misc_keys(monkeypatch):
    _stub_body(monkeypatch, lines=200)
    monkeypatch.setattr(tui, '_set_read', lambda *a, **k: True)
    monkeypatch.setattr(tui.webbrowser, 'open', lambda url: None)
    st = _state('right')
    keys = [ord('l'), ord('d'), ord('u'), ord('g'), ord('G'),
            ord('o'), ord('r'), ord('x'), 13, ord('q')]
    tui._loop(FakeScreen(keys=keys), st, "base", "tok", False, {})


def test_loop_reader_misc_keys(monkeypatch):
    import curses as _c
    _stub_body(monkeypatch, lines=100)
    monkeypatch.setattr(tui, '_set_read', lambda *a, **k: True)
    monkeypatch.setattr(tui.webbrowser, 'open', lambda url: None)
    st = _state('off')
    keys = [13, ord('j'), ord('k'), ord(' '), _c.KEY_PPAGE, ord('g'), ord('G'),
            ord('o'), ord('r'), ord('x'), ord('q'), ord('q')]
    tui._loop(FakeScreen(keys=keys), st, "base", "tok", False, {})
    assert st.mode == 'list'


def test_loop_menu_misc_keys():
    import curses as _c
    st = _state('off')
    keys = [27, _c.KEY_DOWN, _c.KEY_UP, ord('k'), ord('x'), 27, ord('q')]
    tui._loop(FakeScreen(keys=keys), st, "base", "tok", False, {})
    assert st.menu_open is False


def test_fetch_body_normalizes(monkeypatch):
    raw = {"Id": "m1", "Subject": "S",
           "Body": {"ContentType": "Text", "Content": "hi"},
           "From": {"EmailAddress": {"Address": "a@b.com"}}}
    monkeypatch.setattr(tui.api_mod, 'api_get', lambda *a, **k: raw)
    assert tui._fetch_body("base", "tok", "m1", False)["id"] == "m1"


def test_fetch_body_none(monkeypatch):
    monkeypatch.setattr(tui.api_mod, 'api_get', lambda *a, **k: None)
    assert tui._fetch_body("base", "tok", "m1", False) is None


# --- edge cases / empty state ----------------------------------------------

def test_pad_and_truncate_edges():
    assert tui._pad("abcdef", 3) == "abc"
    assert tui._pad("ab", 4) == "ab  "
    assert tui._truncate("abc", 0) == ""
    assert tui._truncate("abcde", 2) == "ab"


def test_draw_list_empty_shows_placeholder():
    st = tui._State([], "Inbox", Settings(reading_pane='off'))
    scr = FakeScreen()
    tui._draw_list(scr, st)
    assert '(no messages)' in scr.text()


def test_draw_list_empty_with_pane_does_not_crash():
    st = tui._State([], "Inbox", Settings(reading_pane='right'))
    tui._draw_list(FakeScreen(), st)  # pane path with no selection


def test_draw_list_scrolls_down_to_selection():
    st = _state('off', n=6)
    st.selected = 5
    st.top = 0
    tui._draw_list(FakeScreen(h=6), st)  # tiny height forces a scroll
    assert st.top > 0


def test_draw_list_scrolls_up_to_selection():
    st = _state('off', n=6)
    st.selected = 0
    st.top = 4
    tui._draw_list(FakeScreen(), st)
    assert st.top == 0


def test_open_selected_empty():
    st = tui._State([], "Inbox", Settings())
    tui._open_selected(FakeScreen(), st, "base", "tok", False)
    assert st.mode == 'list'


def test_toggle_read_empty():
    st = tui._State([], "Inbox", Settings())
    tui._toggle_read(st, "base", "tok", False)  # no-op, no crash


def test_open_browser_no_link():
    st = _state('off')
    for m in st.messages:
        m['web_link'] = ''
    tui._open_browser(st)
    assert 'no web link' in st.status


def test_do_search_failure(monkeypatch):
    monkeypatch.setattr(tui, '_prompt', lambda scr, label: 'x')
    monkeypatch.setattr(tui, '_fetch_list', lambda *a, **k: None)
    st = _state('off')
    tui._do_search(FakeScreen(), st, "base", "tok", False)
    assert 'search failed' in st.status


def test_handle_menu_edit_custom_empty_clears(monkeypatch):
    monkeypatch.setattr(tui, '_prompt', lambda scr, label: '')
    monkeypatch.setattr(tui, '_save_config', lambda c: None)
    st = _state('off')
    tui._handle_menu_action(FakeScreen(), st, 'edit_custom', {}, "base", "tok", False)
    assert st.settings.date_custom == ''


def test_safe_addstr_out_of_range_is_noop():
    scr = FakeScreen(h=5, w=10)
    tui._safe_addstr(scr, 99, 0, "x")  # y past the bottom → silently skipped
    assert scr.drawn == []


def test_safe_addstr_swallows_curses_error():
    class Boom(FakeScreen):
        def addstr(self, *a, **k):
            raise tui.curses.error("boom")

    tui._safe_addstr(Boom(), 0, 0, "x")  # curses.error caught, no raise


def test_prompt_returns_none_on_escape():
    class NoneStr(FakeScreen):
        def getstr(self, *a, **k):
            return None

    assert tui._prompt(NoneStr(), 'q: ') is None


def test_move_selection_empty_is_noop():
    st = tui._State([], "Inbox", Settings())
    tui._move_selection(st, 1)
    assert st.selected == 0


def test_ensure_body_no_messages():
    st = tui._State([], "Inbox", Settings(reading_pane='right'))
    tui._ensure_selected_body(FakeScreen(), st, "base", "tok", False)
    assert st.body_cache == {}


def test_ensure_body_fetch_failure_caches_nothing(monkeypatch):
    monkeypatch.setattr(tui, '_draw_list', lambda *a, **k: None)
    monkeypatch.setattr(tui, '_fetch_body', lambda *a, **k: None)
    st = _state('right')
    tui._ensure_selected_body(FakeScreen(), st, "base", "tok", False)
    assert st.body_cache == {}


def test_draw_reader_clamps_top():
    st = _state('off')
    st.reader = [f"l{i}" for i in range(5)]
    st.reader_top = 999
    st.mode = 'reader'
    tui._draw_reader(FakeScreen(), st)
    assert st.reader_top <= 5


def test_draw_menu_clips_to_height():
    st = _state('off')
    st.menu_open = True
    tui._draw_menu(FakeScreen(h=3), st)  # more menu lines than rows → clip
