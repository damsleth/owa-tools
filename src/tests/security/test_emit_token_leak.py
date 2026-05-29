"""owa-graph --curl/--az must not leak a live bearer token by default.

Regression guard for the deferred 2026-05-27 finding: the rendered
shell command used to inline the real access token, so
`owa-graph GET /me --curl | pbcopy` copied a live bearer to the
clipboard. Default output now renders a $OWA_TOKEN placeholder;
--include-token (include_token=True here) is required to inline the
real token.
"""
from owa_core.secrets import contains_secret
from owa_graph import emit

URL = 'https://graph.microsoft.com/v1.0/me'


def _jwt():
    # JWT-shaped value the secret detector recognizes as an access token.
    return '.'.join([
        'eyJhbGciOiJIUzI1NiIs',
        'eyJhdWQiOiJvd2EtdG9vbHMi',
        'c2lnbmF0dXJlZm9ydGVzdHM',
    ])


def test_curl_default_carries_no_jwt():
    out = emit.render_curl('GET', URL, _jwt())
    assert not contains_secret(out)
    assert _jwt() not in out


def test_az_default_carries_no_jwt():
    out = emit.render_az('GET', URL, _jwt())
    assert not contains_secret(out)
    assert _jwt() not in out


def test_curl_include_token_emits_the_jwt():
    out = emit.render_curl('GET', URL, _jwt(), include_token=True)
    assert _jwt() in out


def test_az_include_token_emits_the_jwt():
    out = emit.render_az('GET', URL, _jwt(), include_token=True)
    assert _jwt() in out
