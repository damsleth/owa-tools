"""Additional emit.py coverage: bytes body, scalar body, az with body,
short commands that skip continuation."""
from owa_graph import emit


URL = 'https://graph.microsoft.com/v1.0/me'
TOKEN = 'eyJ0.PAY.SIG'


def test_serialize_body_handles_none_and_bytes():
    assert emit._serialize_body(None) is None
    assert emit._serialize_body(b'hello') == 'hello'
    assert emit._serialize_body(bytearray(b'x')) == 'x'


def test_serialize_body_passes_strings_through():
    assert emit._serialize_body('plain') == 'plain'


def test_serialize_body_compact_json_for_dict():
    out = emit._serialize_body({'a': 1, 'b': 'two'})
    # No whitespace separators.
    assert out == '{"a":1,"b":"two"}'


def test_join_continuation_short_command_one_line():
    # 4 tokens or fewer - returned as a single line.
    out = emit._join_continuation(['curl', '-sS', 'https://x/y'])
    assert out == 'curl -sS https://x/y'
    assert '\n' not in out


def test_curl_no_body_no_content_type():
    out = emit.render_curl('GET', URL, TOKEN)
    assert 'Content-Type' not in out


def test_az_post_with_file_body_keeps_at_path():
    out = emit.render_az(
        'POST', URL, TOKEN,
        body='/tmp/payload.json', body_is_file_ref=True,
    )
    assert '@/tmp/payload.json' in out


def test_az_with_extra_headers_appends_to_headers_arg():
    out = emit.render_az(
        'GET', URL, TOKEN,
        headers={'Prefer': 'odata.maxpagesize=10'},
    )
    assert 'Prefer=odata.maxpagesize=10' in out
    assert 'Authorization=Bearer' in out


def test_curl_with_bytes_body_decodes():
    out = emit.render_curl('POST', URL, TOKEN, body=b'rawbytes')
    assert 'rawbytes' in out
