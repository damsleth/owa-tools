"""Pretty-format tests for owa-people."""

from owa_people.format import format_people_pretty, format_person_pretty


def test_format_people_pretty_empty():
    assert format_people_pretty([]) == "(no matches)"


def test_format_people_pretty_table_truncates_long_fields():
    out = format_people_pretty([
        {
            "displayName": "Ada Lovelace With A Very Long Display Name",
            "email": "ada.lovelace.with.a.very.long.alias@example.com",
            "jobTitle": "Principal Analytical Engine Programmer",
            "companyName": "Example Corporation With A Long Name",
        }
    ])

    assert out.splitlines()[0].startswith("name")
    assert "Ada Lovelace With A Very ..." in out
    assert "ada.lovelace.with.a.very.long.ali..." in out


def test_format_person_pretty_empty():
    assert format_person_pretty(None) == "(no person)"


def test_format_person_pretty_full_record():
    out = format_person_pretty({
        "displayName": "Ada Lovelace",
        "email": "ada@example.com",
        "jobTitle": "Programmer",
        "department": "Research",
        "companyName": "Example Corp",
        "officeLocation": "London",
        "mobilePhone": "+47 123",
        "businessPhones": ["+47 456", "+47 789"],
        "id": "person-1",
    })

    assert out.startswith("Ada Lovelace")
    assert "email:    ada@example.com" in out
    assert "phones:   +47 456, +47 789" in out
    assert "id:       person-1" in out


def test_format_person_pretty_uses_fallback_name():
    assert format_person_pretty({"businessPhones": []}) == "(no name)"
