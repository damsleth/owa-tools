"""Tests for owa_core.tui_kit.layout — pure geometry + text fitting."""
from __future__ import annotations

from owa_core.tui_kit.layout import (
    PLACEMENT_BOTTOM,
    PLACEMENT_OFF,
    PLACEMENT_RIGHT,
    Rect,
    pad,
    regions,
    truncate,
    truncate_ellipsis,
    wrap_body,
)


class TestRegionsOff:
    def test_full_width_no_pane(self):
        r = regions(120, 40, PLACEMENT_OFF, 50)
        assert r.list_rect == Rect(0, 0, 120, 40)
        assert r.pane_rect == Rect(0, 0, 0, 0)

    def test_invalid_placement_falls_back_to_off(self):
        r = regions(120, 40, "diagonal", 50)
        assert r.pane_rect.w == 0

    def test_invalid_ratio_falls_back_to_50(self):
        r = regions(100, 40, PLACEMENT_RIGHT, 33)
        assert r.list_rect.w == 50


class TestRegionsRight:
    def test_split_sums_to_width(self):
        r = regions(100, 40, PLACEMENT_RIGHT, 50)
        assert r.list_rect.w + 1 + r.pane_rect.w == 100

    def test_ratio_40(self):
        r = regions(100, 40, PLACEMENT_RIGHT, 40)
        assert r.list_rect.w == 40

    def test_no_negative_widths_tiny(self):
        r = regions(1, 10, PLACEMENT_RIGHT, 50)
        assert r.list_rect.w >= 0 and r.pane_rect.w >= 0


class TestRegionsBottom:
    def test_split_sums_to_height(self):
        r = regions(120, 40, PLACEMENT_BOTTOM, 50)
        assert r.list_rect.h + 1 + r.pane_rect.h == 40

    def test_pane_y_follows_divider(self):
        r = regions(120, 40, PLACEMENT_BOTTOM, 40)
        assert r.pane_rect.y == r.list_rect.h + 1

    def test_no_negative_heights_tiny(self):
        r = regions(80, 1, PLACEMENT_BOTTOM, 50)
        assert r.list_rect.h >= 0 and r.pane_rect.h >= 0


class TestPad:
    def test_pads_to_width(self):
        assert pad("hi", 5) == "hi   "

    def test_truncates_when_longer(self):
        assert pad("hello world", 5) == "hello"

    def test_exact(self):
        assert pad("hello", 5) == "hello"


class TestTruncate:
    def test_hard_no_ellipsis(self):
        assert truncate("hello", 3) == "hel"

    def test_zero_or_negative(self):
        assert truncate("hello", 0) == ""
        assert truncate("hello", -2) == ""

    def test_shorter_unchanged(self):
        assert truncate("hi", 5) == "hi"


class TestTruncateEllipsis:
    def test_marks_elision(self):
        assert truncate_ellipsis("hello", 3) == "he…"

    def test_fits_unchanged(self):
        assert truncate_ellipsis("hi", 5) == "hi"

    def test_width_one(self):
        assert truncate_ellipsis("hello", 1) == "h"

    def test_zero(self):
        assert truncate_ellipsis("hello", 0) == ""


class TestWrapBody:
    def test_empty(self):
        assert wrap_body("", 40) == []

    def test_line_width_respected(self):
        lines = wrap_body("word " * 30, 40)
        assert all(len(ln) <= 40 for ln in lines)

    def test_blank_lines_preserved(self):
        lines = wrap_body("a\n\nb", 40)
        assert "" in lines

    def test_long_word_breaks(self):
        lines = wrap_body("x" * 100, 20)
        assert all(len(ln) <= 20 for ln in lines)
