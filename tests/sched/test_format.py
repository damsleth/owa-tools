"""Pretty-format tests for owa-sched."""

from owa_sched.format import format_availability_pretty, format_slots_pretty


def test_format_availability_pretty_empty():
    assert format_availability_pretty([]) == "(no attendees)"


def test_format_availability_pretty_error_and_empty_busy():
    out = format_availability_pretty([
        {"email": "a@example.com", "error": "denied"},
        {"email": "b@example.com", "busy": []},
    ])

    assert "a@example.com\n  ERROR: denied" in out
    assert "b@example.com\n  (no busy items in window)" in out


def test_format_availability_pretty_busy_items():
    out = format_availability_pretty([
        {
            "email": "a@example.com",
            "busy": [
                {
                    "start": "2026-05-09T09:00:00",
                    "end": "not-an-iso-date",
                    "status": "busy",
                    "subject": "Planning",
                },
                {
                    "start": None,
                    "end": "2026-05-09T10:00:00",
                    "status": "tentative",
                    "subject": "",
                },
            ],
        }
    ])

    assert "2026-05-09 09:00 - not-an-iso-date [busy] Planning" in out
    assert "- - 2026-05-09 10:00 [tentative]" in out


def test_format_slots_pretty_empty():
    assert format_slots_pretty([]) == "(no open slots)"


def test_format_slots_pretty_formats_slots():
    out = format_slots_pretty([
        ("2026-05-09T09:00:00", "2026-05-09T10:00:00"),
        ("bad", None),
    ])

    assert out.startswith("Open slots:")
    assert "2026-05-09 09:00 - 2026-05-09 10:00" in out
    assert "bad - -" in out
