"""emit.py is pure - test the rendered command shapes directly."""
from owa_graph import emit


TOKEN = 'eyJ0eXAi.PAYLOAD.SIG'
URL = 'https://graph.microsoft.com/v1.0/me'


def test_curl_get_minimal():
    out = emit.render_curl('GET', URL, TOKEN)
    assert 'curl' in out
    assert '-X GET' in out
    assert f"Authorization: Bearer {TOKEN}" in out
    assert URL in out
    assert '--data' not in out


def test_curl_post_with_literal_body():
    body = {'subject': 'hello'}
    out = emit.render_curl('POST', URL, TOKEN, body=body)
    assert '-X POST' in out
    assert 'Content-Type: application/json' in out
    # Literal dict body is shell-quoted; the dict repr lands in the output.
    assert "subject" in out
    assert '--data' in out


def test_curl_post_with_file_ref_keeps_at_path():
    out = emit.render_curl(
        'POST', URL, TOKEN, body='/tmp/mail.json', body_is_file_ref=True
    )
    # Should contain --data <quoted path>, not the file contents.
    assert '/tmp/mail.json' in out
    assert '--data' in out


def test_curl_extra_headers_are_quoted():
    out = emit.render_curl(
        'GET', URL, TOKEN, headers={'Prefer': 'odata.maxpagesize=10'},
    )
    assert "Prefer: odata.maxpagesize=10" in out


def test_curl_url_with_special_chars_is_quoted():
    url = "https://graph.microsoft.com/v1.0/users?$top=5&$filter=startswith(displayName,'A')"
    out = emit.render_curl('GET', url, TOKEN)
    # shlex.quote wraps in single quotes when special chars present.
    assert "'" in out
    assert '$top=5' in out


def test_az_get():
    out = emit.render_az('GET', URL, TOKEN)
    assert 'az rest' in out
    assert '--method get' in out
    assert f'--uri ' in out
    assert f'Authorization=Bearer {TOKEN}' in out


def test_az_post_with_body():
    out = emit.render_az('POST', URL, TOKEN, body={'a': 1})
    assert '--method post' in out
    assert '--body' in out


def test_continuation_format_for_long_commands():
    out = emit.render_curl(
        'PATCH', URL, TOKEN,
        headers={'Prefer': 'return=minimal'},
        body={'isRead': True},
    )
    # Multi-line continuation expected once we have multiple flags.
    assert '\\' in out
