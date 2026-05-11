"""Pretty-format tests for owa-doctor reports."""

from owa_doctor.format import format_report_pretty


def test_format_report_pretty_missing_piggy():
    out = format_report_pretty({"owa_piggy": {"installed": False}})
    assert out == "owa-piggy: NOT FOUND on PATH"


def test_format_report_pretty_full_report():
    report = {
        "owa_piggy": {"installed": True, "version": "0.8.0", "path": "/bin/owa-piggy"},
        "siblings": [
            {"name": "owa-cal", "installed": True, "version": "1.0"},
            {"name": "owa-mail", "installed": False, "version": None},
        ],
        "profiles": [
            {
                "alias": "work",
                "default": True,
                "state": "ok",
                "minutes_remaining": 42,
                "error": None,
            },
            {
                "alias": "bad",
                "default": False,
                "state": "fail",
                "minutes_remaining": None,
                "error": "x" * 80,
            },
        ],
        "summary": {"ok": 2, "warn": 1, "fail": 1},
    }

    out = format_report_pretty(report)

    assert "owa-piggy: ok (0.8.0) at /bin/owa-piggy" in out
    assert "Siblings:" in out
    assert "owa-cal" in out
    assert "missing" in out
    assert "Profiles (audience=graph):" in out
    assert "work" in out
    assert "yes" in out
    assert "x" * 40 in out
    assert "Summary: 2 ok, 1 warn, 1 fail" in out
