"""Tests for owa_mail.tui_sort — pure, no curses, no network."""
from owa_mail.tui_sort import sort_messages

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# A small realistic fixture: 5 messages with varied fields.
MESSAGES = [
    {
        "id": "a",
        "received": "2026-05-01T10:00:00Z",
        "from": "Charlie Brown <charlie@example.com>",
        "subject": "Zebra crossing",
        "is_read": True,
    },
    {
        "id": "b",
        "received": "2026-05-03T08:00:00Z",
        "from": "alice@example.com",
        "subject": "Apple picking",
        "is_read": False,
    },
    {
        "id": "c",
        "received": "2026-05-02T12:00:00Z",
        "from": "Bob Smith <bob@example.com>",
        "subject": "Mango season",
        "is_read": True,
    },
    {
        "id": "d",
        "received": "2026-05-04T16:30:00Z",
        "from": "diana@example.com",
        "subject": "apple watch",  # lowercase, tests casefold
        "is_read": False,
    },
    {
        "id": "e",
        "received": "2026-05-05T07:00:00Z",
        "from": "Eve <eve@example.com>",
        "subject": "Kiwi report",
        "is_read": False,
    },
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def ids(result):
    """Extract the 'id' field from each message in the result list."""
    return [m["id"] for m in result]


# ---------------------------------------------------------------------------
# date_desc
# ---------------------------------------------------------------------------

class TestDateDesc:
    def test_newest_first(self):
        result = sort_messages(MESSAGES, "date_desc")
        assert ids(result) == ["e", "d", "b", "c", "a"]

    def test_returns_new_list(self):
        result = sort_messages(MESSAGES, "date_desc")
        assert result is not MESSAGES

    def test_input_not_mutated(self):
        original_ids = ids(MESSAGES)
        sort_messages(MESSAGES, "date_desc")
        assert ids(MESSAGES) == original_ids


# ---------------------------------------------------------------------------
# date_asc
# ---------------------------------------------------------------------------

class TestDateAsc:
    def test_oldest_first(self):
        result = sort_messages(MESSAGES, "date_asc")
        assert ids(result) == ["a", "c", "b", "d", "e"]


# ---------------------------------------------------------------------------
# sender
# ---------------------------------------------------------------------------

class TestSender:
    def test_alphabetical_by_sender_casefold(self):
        result = sort_messages(MESSAGES, "sender")
        # Casefolded from-strings:
        # "alice@example.com"                     -> a
        # "bob smith <bob@example.com>"            -> b
        # "charlie brown <charlie@example.com>"    -> c
        # "diana@example.com"                      -> d
        # "eve <eve@example.com>"                  -> e
        assert ids(result) == ["b", "c", "a", "d", "e"]

    def test_sender_casefold_is_case_insensitive(self):
        msgs = [
            {"id": "upper", "from": "Zara", "received": "2026-01-01"},
            {"id": "lower", "from": "aardvark", "received": "2026-01-02"},
        ]
        result = sort_messages(msgs, "sender")
        assert ids(result) == ["lower", "upper"]


# ---------------------------------------------------------------------------
# subject
# ---------------------------------------------------------------------------

class TestSubject:
    def test_alphabetical_by_subject_casefold(self):
        result = sort_messages(MESSAGES, "subject")
        # Subjects casefold:
        # "apple picking"  -> b
        # "apple watch"    -> d  (same prefix, 'w' > 'p')
        # "kiwi report"    -> e
        # "mango season"   -> c
        # "zebra crossing" -> a
        assert ids(result) == ["b", "d", "e", "c", "a"]

    def test_subject_case_insensitive(self):
        msgs = [
            {"id": "1", "subject": "Zebra", "received": "2026-01-01"},
            {"id": "2", "subject": "apple", "received": "2026-01-02"},
        ]
        result = sort_messages(msgs, "subject")
        assert ids(result) == ["2", "1"]


# ---------------------------------------------------------------------------
# unread_first
# ---------------------------------------------------------------------------

class TestUnreadFirst:
    def test_unread_before_read(self):
        result = sort_messages(MESSAGES, "unread_first")
        result_ids = ids(result)
        # e, d, b are unread; a, c are read
        unread_ids = {m["id"] for m in MESSAGES if not m.get("is_read")}
        read_ids = {m["id"] for m in MESSAGES if m.get("is_read")}
        first_part = set(result_ids[: len(unread_ids)])
        second_part = set(result_ids[len(unread_ids) :])
        assert first_part == unread_ids
        assert second_part == read_ids

    def test_newest_first_within_unread_group(self):
        result = sort_messages(MESSAGES, "unread_first")
        # Unread: e(2026-05-05), d(2026-05-04), b(2026-05-03) — newest first
        unread_part = [m["id"] for m in result if not m.get("is_read")]
        assert unread_part == ["e", "d", "b"]

    def test_newest_first_within_read_group(self):
        result = sort_messages(MESSAGES, "unread_first")
        # Read: c(2026-05-02), a(2026-05-01)
        read_part = [m["id"] for m in result if m.get("is_read")]
        assert read_part == ["c", "a"]


# ---------------------------------------------------------------------------
# Stability
# ---------------------------------------------------------------------------

class TestStability:
    def test_stable_sort_preserves_order_for_equal_keys(self):
        # Two messages with identical received date, sender, and subject.
        msgs = [
            {"id": "first", "received": "2026-06-01T10:00:00Z", "from": "x@example.com", "subject": "Same"},
            {"id": "second", "received": "2026-06-01T10:00:00Z", "from": "x@example.com", "subject": "Same"},
        ]
        result = sort_messages(msgs, "date_desc")
        # Python sort is stable — original order is preserved for equal keys.
        assert ids(result) == ["first", "second"]

    def test_stable_sort_subject_equal_keys(self):
        msgs = [
            {"id": "first", "subject": "Alpha", "received": "2026-06-01"},
            {"id": "second", "subject": "Alpha", "received": "2026-06-01"},
        ]
        result = sort_messages(msgs, "subject")
        assert ids(result) == ["first", "second"]


# ---------------------------------------------------------------------------
# Missing / None field safety
# ---------------------------------------------------------------------------

class TestMissingFields:
    def test_missing_received_does_not_raise(self):
        msgs = [
            {"id": "no_date", "from": "a@a.com", "subject": "Hi"},
            {"id": "has_date", "received": "2026-01-01T00:00:00Z", "from": "b@b.com", "subject": "Bye"},
        ]
        result = sort_messages(msgs, "date_desc")
        assert len(result) == 2

    def test_none_received_sorts_last_in_date_desc(self):
        msgs = [
            {"id": "has_date", "received": "2026-01-01T00:00:00Z"},
            {"id": "no_date"},
        ]
        result = sort_messages(msgs, "date_desc")
        # The message with a real date should come first (newest first).
        assert ids(result)[0] == "has_date"

    def test_missing_received_sorts_last_in_date_asc(self):
        # date_asc is oldest-first, but missing dates must still sink to the
        # bottom (the module contract), not float to the top.
        msgs = [
            {"id": "no_date"},
            {"id": "old", "received": "2026-01-01T00:00:00Z"},
            {"id": "newer", "received": "2026-03-01T00:00:00Z"},
            {"id": "none_date", "received": None},
        ]
        result = sort_messages(msgs, "date_asc")
        assert ids(result)[:2] == ["old", "newer"]  # real dates, oldest first
        assert set(ids(result)[2:]) == {"no_date", "none_date"}  # missing last

    def test_missing_sender_sorts_last(self):
        msgs = [
            {"id": "no_sender", "received": "2026-01-01"},
            {"id": "has_sender", "from": "alice@example.com", "received": "2026-01-01"},
        ]
        result = sort_messages(msgs, "sender")
        assert ids(result) == ["has_sender", "no_sender"]

    def test_none_sender_sorts_last(self):
        msgs = [
            {"id": "none_sender", "from": None, "received": "2026-01-01"},
            {"id": "has_sender", "from": "bob@example.com", "received": "2026-01-01"},
        ]
        result = sort_messages(msgs, "sender")
        assert ids(result) == ["has_sender", "none_sender"]

    def test_missing_subject_sorts_last(self):
        msgs = [
            {"id": "no_subject", "received": "2026-01-01"},
            {"id": "has_subject", "subject": "Alpha", "received": "2026-01-01"},
        ]
        result = sort_messages(msgs, "subject")
        assert ids(result) == ["has_subject", "no_subject"]

    def test_none_subject_sorts_last(self):
        msgs = [
            {"id": "none_subject", "subject": None},
            {"id": "has_subject", "subject": "Beta"},
        ]
        result = sort_messages(msgs, "subject")
        assert ids(result) == ["has_subject", "none_subject"]

    def test_unread_first_missing_is_read_treated_as_unread(self):
        msgs = [
            {"id": "no_is_read", "received": "2026-05-01T00:00:00Z"},
            {"id": "is_read", "received": "2026-05-02T00:00:00Z", "is_read": True},
        ]
        result = sort_messages(msgs, "unread_first")
        # no_is_read (treated as unread) should come first
        assert ids(result)[0] == "no_is_read"

    def test_missing_received_in_unread_first_does_not_raise(self):
        msgs = [
            {"id": "no_date", "is_read": False},
            {"id": "has_date", "received": "2026-05-01T00:00:00Z", "is_read": False},
        ]
        result = sort_messages(msgs, "unread_first")
        assert len(result) == 2

    def test_all_missing_fields_does_not_raise(self):
        msgs = [{}, {}, {}]
        for key in ("date_desc", "date_asc", "sender", "subject", "unread_first"):
            result = sort_messages(msgs, key)
            assert len(result) == 3

    def test_empty_list_does_not_raise(self):
        for key in ("date_desc", "date_asc", "sender", "subject", "unread_first"):
            result = sort_messages([], key)
            assert result == []


# ---------------------------------------------------------------------------
# Unknown sort_by falls back to date_desc
# ---------------------------------------------------------------------------

class TestUnknownSortBy:
    def test_unknown_key_falls_back_to_date_desc(self):
        result_unknown = sort_messages(MESSAGES, "nonexistent_key")
        result_date_desc = sort_messages(MESSAGES, "date_desc")
        assert ids(result_unknown) == ids(result_date_desc)

    def test_empty_string_falls_back_to_date_desc(self):
        result = sort_messages(MESSAGES, "")
        expected = sort_messages(MESSAGES, "date_desc")
        assert ids(result) == ids(expected)
