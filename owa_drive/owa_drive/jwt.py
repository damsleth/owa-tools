"""Minimal JWT helpers. We never validate signatures; these only read
the payload to tell the user how long a token has left."""
import base64
import json
import time


def decode_jwt_segment(seg):
    pad = '=' * (-len(seg) % 4)
    return json.loads(base64.urlsafe_b64decode(seg + pad))


def token_minutes_remaining(access_token):
    try:
        payload = decode_jwt_segment(access_token.split('.')[1])
        exp = payload.get('exp')
        if not isinstance(exp, (int, float)):
            return None
        return int((exp - time.time()) / 60)
    except Exception:
        return None
