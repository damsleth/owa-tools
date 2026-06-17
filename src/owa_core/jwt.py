"""Minimal JWT helpers. We never validate signatures; these only read
the payload to tell the user how long a token has left and which scopes
it carries.
"""
import base64
import json
import time


def decode_jwt_segment(seg):
    """Base64url-decode a JWT segment and parse it as JSON."""
    pad = '=' * (-len(seg) % 4)
    return json.loads(base64.urlsafe_b64decode(seg + pad))


def token_minutes_remaining(access_token):
    """Minutes until the access token's `exp` claim, or None on any
    parse failure. Used for debug-mode logging."""
    try:
        payload = decode_jwt_segment(access_token.split('.')[1])
        exp = payload.get('exp')
        if not isinstance(exp, (int, float)):
            return None
        return int((exp - time.time()) / 60)
    except Exception:
        return None


def decode_token_audience(access_token):
    """Return the `aud` claim or None on parse failure."""
    try:
        payload = decode_jwt_segment(access_token.split('.')[1])
        return payload.get('aud')
    except Exception:
        return None


def tenant_id(token):
    """Return the `tid` (tenant GUID) claim, or the literal
    'myorganization' when the claim is absent or the token can't be
    decoded. The fallback is Graph's tenant-relative placeholder, so
    callers can splice the result into a URL unconditionally."""
    try:
        payload = decode_jwt_segment(token.split('.')[1])
        tid = payload.get('tid')
        if isinstance(tid, str) and tid:
            return tid
    except Exception:
        pass
    return 'myorganization'


def scopes_in_token(access_token):
    """Return the set of delegated scopes the JWT carries, or an empty
    set on any parse failure.

    AAD puts delegated scopes in the `scp` claim as a space-separated
    string ("Mail.Read User.Read"). App-only tokens use `roles` (a list)
    instead - we accept both shapes since the scope-hint feature is
    advisory rather than authoritative.
    """
    try:
        payload = decode_jwt_segment(access_token.split('.')[1])
        scopes = set()
        scp = payload.get('scp')
        if isinstance(scp, str):
            scopes.update(s for s in scp.split() if s)
        roles = payload.get('roles')
        if isinstance(roles, list):
            scopes.update(r for r in roles if isinstance(r, str))
        return scopes
    except Exception:
        return set()


def scope_in_token(access_token, scope):
    """Convenience predicate: is `scope` present in the JWT's scope set."""
    return scope in scopes_in_token(access_token)
