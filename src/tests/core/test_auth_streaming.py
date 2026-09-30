"""owa_core.auth._run_streaming: broker stderr is echoed live, still collected."""
import sys

from owa_core import auth


def test_run_streaming_echoes_progress_and_holds_back_errors(capsys):
    script = (
        "import sys\n"
        "print('[nc] refresh token expired; auto-reseeding...', file=sys.stderr, flush=True)\n"
        "print('ERROR: AADSTS70043 fake', file=sys.stderr, flush=True)\n"
        "print('{\"access_token\": \"x\"}')\n"
    )
    proc, stderr_text = auth._run_streaming(
        [sys.executable, '-c', script], label='owa-piggy[nc]', timeout=30,
    )
    err = capsys.readouterr().err
    assert proc.returncode == 0 and proc.stdout.strip() == '{"access_token": "x"}'
    assert 'owa-piggy[nc]: [nc] refresh token expired; auto-reseeding...' in err
    assert 'AADSTS70043' not in err  # surfaced once, by the caller's exception
    assert 'ERROR: AADSTS70043 fake' in stderr_text


def test_run_streaming_redacts_echoed_lines(capsys):
    jwt = '.'.join(['eyJhbGciOiJIUzI1NiIs', 'eyJhdWQiOiJvd2EtdG9vbHMi', 'c2lnbmF0dXJlZm9ydGVzdHM'])
    auth._run_streaming(
        [sys.executable, '-c', f"import sys; print('token {jwt}', file=sys.stderr)"],
        label='owa-piggy', timeout=30,
    )
    err = capsys.readouterr().err
    assert jwt not in err and '[redacted-secret]' in err


def test_broker_error_prefers_error_lines():
    text = "[nc] auto-reseeding...\nERROR: AADSTS70043 fake\n"
    assert auth._broker_error(text) == 'AADSTS70043 fake'
    assert auth._broker_error('boom\n') == 'boom'
    assert auth._broker_error('') == 'token refresh failed'
