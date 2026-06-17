"""Canonical keybinding table shared by every owa-* TUI.

One source of truth so ``j/k``, the arrows, ``enter``, ``esc``, ``q``, ``r``
and ``/`` mean the same thing in every tool's TUI. Adapters test membership::

    if ch in keys.DOWN:
        ...

Each name is a ``frozenset`` of key codes (so an adapter can combine them);
``ESC`` is a bare int because it is compared directly. Pure module — importing
``curses`` only reads its key-code constants, it does not initialise a screen.
"""
from __future__ import annotations

import curses

# --- vertical movement ------------------------------------------------------
UP = frozenset({ord('k'), curses.KEY_UP})
DOWN = frozenset({ord('j'), curses.KEY_DOWN})
HALF_UP = frozenset({ord('u')})
HALF_DOWN = frozenset({ord('d')})
PAGE_UP = frozenset({curses.KEY_PPAGE})
PAGE_DOWN = frozenset({curses.KEY_NPAGE, ord(' ')})
TOP = frozenset({ord('g')})
BOTTOM = frozenset({ord('G')})

# --- horizontal / drill -----------------------------------------------------
LEFT = frozenset({ord('h'), curses.KEY_LEFT})
RIGHT = frozenset({ord('l'), curses.KEY_RIGHT})
ENTER = frozenset({curses.KEY_ENTER, 10, 13})

# Drill into the selected item (enter or →); pop back out (← or backspace).
DRILL = ENTER | RIGHT
BACK = LEFT | frozenset({curses.KEY_BACKSPACE, 127, 8})

# --- actions ----------------------------------------------------------------
SEARCH = frozenset({ord('/')})
REFRESH = frozenset({ord('r')})
QUIT = frozenset({ord('q')})
ESC = 27
