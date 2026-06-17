"""Shared, dependency-free curses TUI kit for the owa-* suite.

Every per-tool TUI is a thin adapter on top of this kit, so the suite shares
one look-and-feel and one event loop. Modules:

    layout    pure geometry + text fitting (no curses)
    keys      canonical keybinding table
    screen    safe curses drawing + line input
    settings  generic view-settings cycle/persist engine
    menu      generic esc-overlay menu state machine
    app       generic list+detail browser loop (the callback contract)

owa_core stays domain-neutral and stdlib-only; nothing here imports a tool
package.
"""
from __future__ import annotations

from . import app, keys, layout, menu, screen, settings

__all__ = ["app", "keys", "layout", "menu", "screen", "settings"]
