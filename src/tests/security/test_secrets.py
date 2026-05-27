"""Secret redaction and scanner tests."""
import json

from owa_core.errors import AuthExpiredError, emit_error
from owa_core.secrets import (
    BODY_REDACTION,
    REDACTION,
    contains_secret,
    find_secret_shapes,
    redact,
)


def _jwt():
    return '.'.join([
        'eyJhbGciOiJIUzI1NiIs',
        'eyJhdWQiOiJvd2EtdG9vbHMi',
        'c2lnbmF0dXJlZm9ydGVzdHM',
    ])


def _refresh():
    return '1.AQ' + 'a' * 24


def test_redact_access_refresh_and_client_secret_shapes():
    secret_key = 'client' + '_secret'
    text = (
        f'Authorization: Bearer {_jwt()}\n'
        f'refresh={_refresh()}\n'
        f'{secret_key}="supersecretvalue123"'
    )
    out = redact(text)
    assert _jwt() not in out
    assert _refresh() not in out
    assert 'supersecretvalue123' not in out
    assert out.count(REDACTION) == 3


def test_redact_scrubs_message_body_fields():
    # A Graph sendMail-shaped payload: the message content must be
    # scrubbed, the harmless ContentType metadata left intact.
    payload = {'Message': {'Body': {'ContentType': 'Text', 'Content': 'secret CANARY_xyz here'}}}
    out = redact(json.dumps(payload))
    assert 'CANARY_xyz' not in out
    assert BODY_REDACTION in out
    assert 'ContentType' in out and 'Text' in out  # metadata preserved


def test_redact_body_field_variants():
    for key in ('body', 'content', 'text', 'html_body', 'plain_body'):
        out = redact(json.dumps({key: 'LEAK_me'}))
        assert 'LEAK_me' not in out, key
        assert BODY_REDACTION in out, key


def test_redact_leaves_non_body_keys_alone():
    out = redact(json.dumps({'subject': 'keep this', 'contentType': 'HTML'}))
    assert 'keep this' in out
    assert 'HTML' in out
    assert BODY_REDACTION not in out


def test_find_secret_shapes_reports_kinds():
    findings = find_secret_shapes(f'Bearer {_jwt()} and refresh {_refresh()}')
    assert sorted(finding.kind for finding in findings) == ['access_token', 'refresh_token']
    assert contains_secret(_jwt()) is True
    assert contains_secret('owa-piggy 0.7.1') is False


def test_emit_error_redacts_message_and_hint(capsys):
    error = AuthExpiredError(
        f'broker returned {_jwt()}',
        remediation=f'reseed without using {_refresh()}',
    )
    code = emit_error(error)
    err = capsys.readouterr().err
    assert code == 11
    assert _jwt() not in err
    assert _refresh() not in err
    assert err.count(REDACTION) == 2
