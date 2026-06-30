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


def test_format_report_pretty_unreachable_piggy():
    out = format_report_pretty({
        "owa_piggy": {"installed": True, "reachable": False, "path": "/bin/owa-piggy"},
    })
    assert "UNREACHABLE" in out
    assert "/bin/owa-piggy" in out


def test_format_report_pretty_audience_mismatch_note():
    report = {
        "owa_piggy": {"installed": True, "reachable": True, "version": "0.8.0", "path": "/p"},
        "profiles": [{
            "alias": "work", "default": True, "state": "warn",
            "minutes_remaining": 50, "audience_mismatch": True,
            "token_audience": "https://outlook.office.com", "error": None,
        }],
        "summary": {"ok": 0, "warn": 1, "fail": 0},
    }
    out = format_report_pretty(report)
    assert "audience mismatch" in out


def test_format_report_pretty_coverage_section():
    report = {
        "owa_piggy": {"installed": True, "reachable": True, "version": "0.8.0", "path": "/p"},
        "profiles": [
            {"alias": "work", "default": True, "state": "ok",
             "minutes_remaining": 60, "error": None,
             "coverage": {"graph": True, "outlook": False}},
        ],
        "summary": {"ok": 1, "warn": 0, "fail": 0},
    }
    out = format_report_pretty(report)
    assert "Coverage (audiences obtainable):" in out
    assert "graph" in out
    assert "outlook" in out
    assert "yes" in out
    assert "no" in out
