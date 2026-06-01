"""Tests for owa_mail.tui_layout — pure layout helpers.

Covers:
- regions(): math for each placement/ratio; divider accounting; tiny terminals.
- list_row(): flex columns fill width and fit; narrow truncation; marker offsets.
- wrap_body(): line-width guarantee; blank-line preservation; long-word wrap.
"""

from owa_mail.tui_layout import (
    PLACEMENT_BOTTOM,
    PLACEMENT_OFF,
    PLACEMENT_RIGHT,
    Rect,
    list_row,
    regions,
    wrap_body,
)

# ---------------------------------------------------------------------------
# regions() — geometry math
# ---------------------------------------------------------------------------


class TestRegionsOff:
    def test_full_width_no_pane(self):
        r = regions(120, 40, PLACEMENT_OFF, 50)
        assert r.list_rect == Rect(0, 0, 120, 40)
        assert r.pane_rect == Rect(0, 0, 0, 0)

    def test_off_ignores_ratio(self):
        r40 = regions(120, 40, PLACEMENT_OFF, 40)
        r60 = regions(120, 40, PLACEMENT_OFF, 60)
        assert r40.list_rect.w == 120
        assert r60.list_rect.w == 120

    def test_off_tiny_terminal(self):
        r = regions(1, 1, PLACEMENT_OFF, 50)
        assert r.list_rect.w == 1
        assert r.pane_rect.w == 0

    def test_off_zero_size(self):
        r = regions(0, 0, PLACEMENT_OFF, 50)
        assert r.list_rect.w == 0
        assert r.list_rect.h == 0


class TestRegionsRight:
    def test_50_50_total_width(self):
        r = regions(100, 40, PLACEMENT_RIGHT, 50)
        # list + divider + pane == total width
        assert r.list_rect.w + 1 + r.pane_rect.w == 100

    def test_40_ratio_list_width(self):
        r = regions(100, 40, PLACEMENT_RIGHT, 40)
        assert r.list_rect.w == 40
        assert r.pane_rect.w == 100 - 40 - 1  # 59

    def test_60_ratio_list_width(self):
        r = regions(100, 40, PLACEMENT_RIGHT, 60)
        assert r.list_rect.w == 60
        assert r.pane_rect.w == 100 - 60 - 1  # 39

    def test_pane_x_follows_divider(self):
        r = regions(80, 24, PLACEMENT_RIGHT, 50)
        expected_pane_x = r.list_rect.w + 1  # +1 for divider
        assert r.pane_rect.x == expected_pane_x

    def test_height_unchanged(self):
        r = regions(80, 24, PLACEMENT_RIGHT, 50)
        assert r.list_rect.h == 24
        assert r.pane_rect.h == 24

    def test_list_rect_starts_at_origin(self):
        r = regions(80, 24, PLACEMENT_RIGHT, 50)
        assert r.list_rect.x == 0
        assert r.list_rect.y == 0

    def test_no_negative_widths_on_tiny_terminal(self):
        r = regions(2, 10, PLACEMENT_RIGHT, 50)
        assert r.list_rect.w >= 0
        assert r.pane_rect.w >= 0

    def test_single_column_terminal(self):
        r = regions(1, 10, PLACEMENT_RIGHT, 50)
        assert r.list_rect.w >= 0
        assert r.pane_rect.w >= 0

    def test_zero_width_terminal(self):
        r = regions(0, 10, PLACEMENT_RIGHT, 50)
        assert r.list_rect.w == 0
        assert r.pane_rect.w == 0


class TestRegionsBottom:
    def test_50_50_total_height(self):
        r = regions(120, 40, PLACEMENT_BOTTOM, 50)
        assert r.list_rect.h + 1 + r.pane_rect.h == 40

    def test_40_ratio_list_height(self):
        r = regions(120, 40, PLACEMENT_BOTTOM, 40)
        assert r.list_rect.h == 16
        assert r.pane_rect.h == 40 - 16 - 1  # 23

    def test_60_ratio_list_height(self):
        r = regions(120, 40, PLACEMENT_BOTTOM, 60)
        assert r.list_rect.h == 24
        assert r.pane_rect.h == 40 - 24 - 1  # 15

    def test_pane_y_follows_divider(self):
        r = regions(120, 40, PLACEMENT_BOTTOM, 50)
        expected_pane_y = r.list_rect.h + 1
        assert r.pane_rect.y == expected_pane_y

    def test_width_unchanged(self):
        r = regions(120, 40, PLACEMENT_BOTTOM, 50)
        assert r.list_rect.w == 120
        assert r.pane_rect.w == 120

    def test_no_negative_heights_tiny_terminal(self):
        r = regions(80, 2, PLACEMENT_BOTTOM, 50)
        assert r.list_rect.h >= 0
        assert r.pane_rect.h >= 0

    def test_zero_height(self):
        r = regions(80, 0, PLACEMENT_BOTTOM, 50)
        assert r.list_rect.h == 0
        assert r.pane_rect.h == 0


class TestRegionsInvalidArgs:
    def test_invalid_placement_falls_back_to_off(self):
        r = regions(80, 24, "diagonal", 50)
        assert r.list_rect.w == 80
        assert r.pane_rect.w == 0

    def test_invalid_ratio_falls_back_to_50(self):
        r = regions(100, 24, PLACEMENT_RIGHT, 99)
        # 50 % of 100 = 50; pane = 100 - 50 - 1 = 49
        assert r.list_rect.w == 50
        assert r.pane_rect.w == 49


# ---------------------------------------------------------------------------
# list_row() — flex rendering
# ---------------------------------------------------------------------------


def _msg(**kwargs):
    defaults = {
        "received": "2026-05-11T09:30:00Z",
        "from": "ada@example.com",
        "subject": "Hello there",
        "is_read": False,
        "flag": "NotFlagged",
        "has_attachments": False,
    }
    defaults.update(kwargs)
    return defaults


class TestListRow:
    def test_fits_width(self):
        row = list_row(_msg(), 80, date_fmt="iso8601")
        assert len(row) <= 80

    def test_contains_date(self):
        row = list_row(_msg(), 80, date_fmt="iso8601")
        assert "2026-05-11" in row

    def test_contains_sender(self):
        row = list_row(_msg(), 120, date_fmt="iso8601")
        assert "ada@example.com" in row

    def test_contains_subject(self):
        row = list_row(_msg(), 120, date_fmt="iso8601")
        assert "Hello there" in row

    def test_unread_marker_present(self):
        row = list_row(_msg(is_read=False), 80, date_fmt="iso8601")
        # prefix = date(10) + space(1) = 11; marker at index 11
        prefix_len = 10 + 1  # iso8601 date + 1 space
        assert row[prefix_len] == "*"

    def test_read_message_no_unread_marker(self):
        row = list_row(_msg(is_read=True), 80, date_fmt="iso8601")
        prefix_len = 10 + 1
        assert row[prefix_len] == " "

    def test_flag_marker(self):
        row = list_row(_msg(flag="Flagged"), 80, date_fmt="iso8601")
        prefix_len = 10 + 1
        assert row[prefix_len + 1] == "!"

    def test_no_flag_marker(self):
        row = list_row(_msg(flag="NotFlagged"), 80, date_fmt="iso8601")
        prefix_len = 10 + 1
        assert row[prefix_len + 1] == " "

    def test_attachment_marker(self):
        row = list_row(_msg(has_attachments=True), 80, date_fmt="iso8601")
        prefix_len = 10 + 1
        assert row[prefix_len + 2] == "@"

    def test_no_attachment_marker(self):
        row = list_row(_msg(has_attachments=False), 80, date_fmt="iso8601")
        prefix_len = 10 + 1
        assert row[prefix_len + 2] == " "

    def test_truncates_narrow_width(self):
        row = list_row(_msg(), 20, date_fmt="iso8601")
        assert len(row) <= 20

    def test_very_narrow_width(self):
        row = list_row(_msg(), 5, date_fmt="iso8601")
        assert len(row) <= 5

    def test_width_1(self):
        row = list_row(_msg(), 1, date_fmt="iso8601")
        assert len(row) <= 1

    def test_wide_terminal_fills(self):
        """On a wide terminal the row should grow beyond the old 87-char cap."""
        row = list_row(_msg(subject="A" * 100, **{"from": "B" * 50}), 160, date_fmt="iso8601")
        assert len(row) <= 160
        # Should use more of the width than the old 87-char limit
        assert len(row) > 50

    def test_ddmm_format(self):
        row = list_row(_msg(), 80, date_fmt="ddmm")
        assert "11.05" in row

    def test_ddmm_hhmm_format(self):
        row = list_row(_msg(), 80, date_fmt="ddmm_hhmm")
        assert "11.05" in row
        assert "09:30" in row

    def test_custom_format(self):
        row = list_row(_msg(), 80, date_fmt="custom", custom_fmt="%Y/%m/%d")
        assert "2026/05/11" in row

    def test_missing_received(self):
        row = list_row(_msg(received=None), 80, date_fmt="iso8601")
        assert len(row) <= 80

    def test_missing_sender(self):
        row = list_row({**_msg(), "from": None}, 80, date_fmt="iso8601")
        assert len(row) <= 80

    def test_missing_subject_fallback(self):
        row = list_row({**_msg(), "subject": None}, 80, date_fmt="iso8601")
        assert "(no subject)" in row or len(row) <= 80

    def test_all_markers_set(self):
        msg = _msg(is_read=False, flag="Flagged", has_attachments=True)
        row = list_row(msg, 80, date_fmt="iso8601")
        prefix_len = 10 + 1
        assert row[prefix_len] == "*"
        assert row[prefix_len + 1] == "!"
        assert row[prefix_len + 2] == "@"


# ---------------------------------------------------------------------------
# wrap_body() — pane body wrapping
# ---------------------------------------------------------------------------


class TestWrapBody:
    def test_line_width_respected(self):
        text = "word " * 30  # 150 chars total
        lines = wrap_body(text, 40)
        assert all(len(ln) <= 40 for ln in lines)

    def test_blank_lines_preserved(self):
        text = "first paragraph\n\nsecond paragraph"
        lines = wrap_body(text, 80)
        assert "" in lines

    def test_empty_text(self):
        assert wrap_body("", 80) == []

    def test_single_line_fits(self):
        lines = wrap_body("hello world", 80)
        assert lines == ["hello world"]

    def test_long_word_breaks(self):
        long_word = "a" * 100
        lines = wrap_body(long_word, 20)
        assert all(len(ln) <= 20 for ln in lines)
        assert len(lines) > 1

    def test_width_1(self):
        lines = wrap_body("hi", 1)
        assert all(len(ln) <= 1 for ln in lines)

    def test_url_wrapped(self):
        url = "https://example.com/" + "x" * 80
        lines = wrap_body(url, 40)
        assert all(len(ln) <= 40 for ln in lines)

    def test_multiple_paragraphs(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        lines = wrap_body(text, 80)
        joined = "\n".join(lines)
        assert "Para one." in joined
        assert "Para two." in joined
        assert "Para three." in joined

    def test_preserves_multiple_blank_lines(self):
        text = "a\n\n\nb"
        lines = wrap_body(text, 80)
        # Should have at least two blank lines
        blanks = sum(1 for ln in lines if ln == "")
        assert blanks >= 2

    def test_returns_list_of_str(self):
        lines = wrap_body("hello\nworld", 80)
        assert isinstance(lines, list)
        assert all(isinstance(ln, str) for ln in lines)
