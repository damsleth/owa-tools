"""Layout helpers for the owa-mail TUI overhaul.

All functions are pure (no curses, no I/O).

Public API
----------
regions(width, height, placement, ratio) -> Regions
    Compute list-rect and pane-rect for the given terminal size.

list_row(msg, width, *, date_fmt, custom_fmt='') -> str
    Render one message as a single flex-width list row, len <= width.

wrap_body(text, width) -> list[str]
    Hard-wrap body text for the reading pane (preserves blank lines,
    footnote-link lines included).
"""
from __future__ import annotations

# Geometry + text-fitting primitives now live in owa_core.tui_kit.layout;
# re-exported here so existing owa_mail.tui_layout import sites keep working.
# list_row + date formatting below stay mail-specific.
from owa_core.tui_kit.layout import (  # noqa: F401
    PLACEMENT_BOTTOM,
    PLACEMENT_OFF,
    PLACEMENT_RIGHT,
    Rect,
    Regions,
    regions,
    wrap_body,
)
from owa_core.tui_kit.layout import truncate_ellipsis as _truncate

# ---------------------------------------------------------------------------
# Optional import of tui_dates (U2 module).  If that agent hasn't landed yet
# we fall back to a minimal inline formatter that covers the same contract.
# ---------------------------------------------------------------------------
try:
    from owa_mail.tui_dates import format_received as _format_received
except ImportError:  # pragma: no cover — only during parallel development

    def _format_received(iso: str, fmt: str, custom: str = "") -> str:  # type: ignore[misc]
        """Minimal fallback: iso8601 or plain date prefix."""
        if not iso:
            return ""
        date = iso.split("T")[0] if "T" in iso else iso
        time_part = ""
        if "T" in iso:
            time_part = ":".join(iso.split("T")[1].split(":")[:2])
        if fmt == "ddmm":
            parts = date.split("-")
            return f"{parts[2]}.{parts[1]}" if len(parts) == 3 else date
        if fmt == "ddmm_hhmm":
            parts = date.split("-")
            d = f"{parts[2]}.{parts[1]}" if len(parts) == 3 else date
            return f"{d} {time_part}" if time_part else d
        if fmt == "custom" and custom:
            from datetime import datetime

            try:
                dt = datetime.fromisoformat(iso.rstrip("Z"))
                return dt.strftime(custom)
            except Exception:
                return date
        return date  # iso8601 or unknown fmt


# ---------------------------------------------------------------------------
# list_row
# ---------------------------------------------------------------------------

# Fixed-width prefix fields:
#   date portion  (varies by fmt: 10 for iso8601/ddmm_hhmm, 5 for ddmm, …)
# We use _DATE_COLS as the *maximum* column budget; actual formatted string
# is padded / truncated to that width.
_DATE_FMT_WIDTHS = {
    "iso8601": 10,      # YYYY-MM-DD
    "ddmm": 5,          # DD.MM
    "ddmm_hhmm": 11,    # DD.MM HH:MM
    "custom": 10,       # reasonable default for unknown custom
}
_TIME_COLS = 0          # time is included inline for ddmm_hhmm; no extra col
_MARKER_COLS = 3        # '*', '!', '@'
_SPACE_AFTER_DATE = 1
_SPACE_AFTER_MARKERS = 1


def _date_width(fmt: str) -> int:
    return _DATE_FMT_WIDTHS.get(fmt, 10)


# _truncate is imported from owa_core.tui_kit.layout (truncate_ellipsis).


def list_row(
    msg: dict,
    width: int,
    *,
    date_fmt: str = "iso8601",
    custom_fmt: str = "",
) -> str:
    """Render one message as a single flex-width list row.

    Layout:
        <date>  <*!@>  <sender padded ~30%>  <subject fills rest>

    The final string is hard-truncated so len(result) <= width.
    """
    width = max(width, 1)

    # --- date field (fixed width per format) ---
    date_w = _date_width(date_fmt)
    received = msg.get("received") or ""
    date_str = _format_received(received, date_fmt, custom_fmt)
    # Pad or truncate to exactly date_w cols
    if len(date_str) < date_w:
        date_str = date_str.ljust(date_w)
    else:
        date_str = date_str[:date_w]

    # --- markers: unread(*), flag(!), attachment(@) ---
    marker = "*" if not msg.get("is_read") else " "
    flag = "!" if msg.get("flag") == "Flagged" else " "
    att = "@" if msg.get("has_attachments") else " "
    markers = f"{marker}{flag}{att}"

    # --- fixed-width prefix ---
    prefix = f"{date_str} {markers} "
    prefix_len = len(prefix)  # date_w + 1 + 3 + 1

    remaining = width - prefix_len
    if remaining <= 0:
        # terminal too narrow for anything beyond prefix
        return _truncate(prefix, width)

    # --- flex sender + subject ---
    # Sender gets ~30 % of remaining, minimum 10, subject gets the rest.
    # We leave 2 chars between sender and subject ("  ").
    sep = "  "
    sep_len = len(sep)
    sender_budget = max(min(int(remaining * 0.30), remaining - sep_len - 1), 0)
    subject_budget = max(remaining - sender_budget - sep_len, 0)

    sender_raw = msg.get("from") or ""
    subject_raw = msg.get("subject") or "(no subject)"

    if sender_budget <= 0 and subject_budget <= 0:
        return _truncate(prefix, width)

    if sender_budget <= 0:
        row = prefix + _truncate(subject_raw, subject_budget)
    elif subject_budget <= 0:
        row = prefix + _truncate(sender_raw, sender_budget)
    else:
        sender_col = _truncate(sender_raw, sender_budget).ljust(sender_budget)
        subject_col = _truncate(subject_raw, subject_budget)
        row = prefix + sender_col + sep + subject_col

    # Final safety truncation
    return _truncate(row, width)


# ---------------------------------------------------------------------------
# wrap_body
# ---------------------------------------------------------------------------


# wrap_body is imported from owa_core.tui_kit.layout (re-exported above).
