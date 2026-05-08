"""Secret redaction and scanner tests."""
from owa_core.errors import AuthExpiredError, emit_error
from owa_core.secrets import REDACTION, contains_secret, find_secret_shapes, redact


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
