import json

import pytest

from owa_core.secrets import redact


@pytest.mark.parametrize('body', ['plain', 'say "secret suffix"', '\\"quoted', 'line\nnext', 'a\\b', '"' * 30])
@pytest.mark.parametrize('key', ['body', 'Content', 'text', 'html_body', 'plain_body'])
def test_json_body_redaction_handles_escapes(body, key):
    source = json.dumps({'nested': {key: body, 'contentType': 'Text'}})
    result = json.loads(redact(source))
    assert result == {'nested': {key: '[redacted-body]', 'contentType': 'Text'}}


def test_truncated_json_body_redacts_remainder():
    result = redact('{"content": "prefix \\"private suffix')
    assert 'private' not in result and 'prefix' not in result


def test_truncated_json_escape_redacts_remainder():
    assert redact('{"content": "private suffix' + chr(92)) == '{"content": "[redacted-body]"'
