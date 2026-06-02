"""HTTP helpers for owa-teams over owa_core.http.

Two doors share one error policy: parsed JSON on 2xx, None on recoverable
failures (already reported to stderr), and re-raise on auth/scope so the
dispatcher maps them to the shared exit-code taxonomy.

  * `graph_get` / `graph_paginate` - the Graph enumeration surface. Graph
    collections page via `@odata.nextLink`, so `graph_paginate` reuses the
    shared `owa_core.http.paginate`.
  * `chatsvc_messages` - the chat service. Its message stream is
    `{messages: [...], _metadata: {backwardLink}}`, NOT `{value, @odata...}`,
    so the shared paginator does not apply: we follow `_metadata.backwardLink`
    (an absolute URL, the older-messages cursor) ourselves, like owa-sites'
    `paginate_sp`.
"""
from owa_core import http
from owa_core.errors import (
    AuthExpiredError,
    ConflictError,
    InternalError,
    NetworkError,
    NotFoundError,
    OwaError,
    RateLimitedError,
    ScopeInsufficientError,
    emit_error,
)

from . import teams as teams_mod

_RECOVERABLE = (ConflictError, InternalError, NetworkError, NotFoundError, RateLimitedError)
_ACCEPT_JSON = {'Accept': 'application/json'}


def graph_get(base, endpoint, access_token, debug=False):
    url = f'{base}/{endpoint.lstrip("/")}'
    try:
        return http.request('GET', url, token=access_token, debug=debug).json
    except (AuthExpiredError, ScopeInsufficientError):
        raise
    except _RECOVERABLE as error:
        emit_error(error)
        return None
    except OwaError as error:
        emit_error(error)
        return None


def graph_paginate(base, endpoint, access_token, debug=False, max_pages=50):
    """Collect a Graph `value` collection across `@odata.nextLink` pages."""
    url = f'{base}/{endpoint.lstrip("/")}'
    try:
        return list(http.paginate(url, token=access_token, max_pages=max_pages, debug=debug))
    except (AuthExpiredError, ScopeInsufficientError):
        raise
    except _RECOVERABLE as error:
        emit_error(error)
        return None
    except OwaError as error:
        emit_error(error)
        return None


def chatsvc_messages(base, conversation_id, access_token, *, page_size=50, max_pages=20, debug=False):
    """Fetch a conversation's chatsvc message stream, following backwardLink.

    Returns the concatenated raw `messages` (newest-first across pages), or
    None on a recoverable error. Bounded by `max_pages` so an enormous channel
    can't page forever; callers that need a time window pass a small page count
    and filter by timestamp downstream.
    """
    url = teams_mod.conversation_messages_url(base, conversation_id, page_size=page_size)
    collected = []
    pages = 0
    try:
        while url:
            resp = http.request('GET', url, token=access_token, headers=_ACCEPT_JSON, debug=debug)
            payload = resp.json if isinstance(resp.json, dict) else {}
            messages = payload.get('messages')
            if not isinstance(messages, list):
                break
            collected.extend(messages)
            url = (payload.get('_metadata') or {}).get('backwardLink') or ''
            pages += 1
            if pages >= max_pages:
                break
        return collected
    except (AuthExpiredError, ScopeInsufficientError):
        raise
    except _RECOVERABLE as error:
        emit_error(error)
        return None
    except OwaError as error:
        emit_error(error)
        return None
