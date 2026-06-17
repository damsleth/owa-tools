"""Curses primitives shared by owa-* TUIs: safe drawing + line input.

Terminal-bound but tool-neutral. The only module outside an adapter that
touches a curses window directly. Tested via a fake screen object, so the
helpers must never assume a real terminal beyond the ``curses`` calls below.
"""
from __future__ import annotations

import contextlib
import curses
import os


@contextlib.contextmanager
def silence_os_fds():
    """Redirect OS stdout/stderr (fds 1 & 2) to /dev/null for the block.

    Subprocesses spawned inside (a browser launcher, a clipboard helper)
    inherit the silenced descriptors, so a stray diagnostic line can't land on
    the raw terminal and corrupt the curses frame — something a Python-level
    ``sys.stderr`` swap can't prevent. Best-effort: if the dup/dup2 dance fails
    it degrades to a no-op rather than raising.
    """
    saved = None
    devnull = None
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        saved = (os.dup(1), os.dup(2))
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
    except OSError:
        saved = None
    try:
        yield
    finally:
        if saved is not None:
            saved_out, saved_err = saved
            os.dup2(saved_out, 1)
            os.dup2(saved_err, 2)
            os.close(saved_out)
            os.close(saved_err)
        if devnull is not None:
            os.close(devnull)


def safe_addstr(win, y, x, text, attr=0):
    """``addstr`` that clips to the window width and never raises.

    curses raises if you write to (or past) the bottom-right cell; we would
    rather silently clip than crash a viewer.
    """
    height, width = win.getmaxyx()
    if y < 0 or y >= height or x >= width:
        return
    text = text[: max(width - x - 1, 0)]
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def prompt(stdscr, label):
    """Read a line of input at the bottom of the screen.

    Returns the entered string (possibly empty), or ``None`` if input could
    not be read.
    """
    height, width = stdscr.getmaxyx()
    curses.curs_set(1)
    curses.echo()
    safe_addstr(stdscr, height - 1, 0, ' ' * (width - 1))
    safe_addstr(stdscr, height - 1, 0, label)
    stdscr.refresh()
    try:
        raw = stdscr.getstr(height - 1, len(label), max(width - len(label) - 1, 1))
    finally:
        curses.noecho()
        curses.curs_set(0)
    if raw is None:
        return None
    return raw.decode('utf-8', 'replace').strip()


def init_colors(stdscr):
    """Hide the cursor and set a default-color background; best-effort.

    Swallows ``curses.error`` so a colour-less terminal still runs. Also
    enables keypad mode so arrow/page keys arrive as ``KEY_*`` codes.
    """
    curses.curs_set(0)
    try:
        curses.use_default_colors()
        curses.init_pair(1, -1, -1)
        stdscr.bkgd(' ', curses.color_pair(1))
    except curses.error:
        pass
    stdscr.keypad(True)
