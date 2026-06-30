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
)

from . import teams as teams_mod

_RECOVERABLE = (ConflictError, InternalError, NetworkError, NotFoundError, RateLimitedError)
_ACCEPT_JSON = {'Accept': 'application/json'}

# Teams reads fan out many calls (one per team, per channel, and per message
# page), which bursts enough requests to trip chatsvc's rate limiter. Give
# every read a Retry-After-honoring budget by default so a transient 429 is
# ridden through in-process (owa_core.http waits the server-directed delay,
# capped at 60s) rather than aborting the whole verb and dropping a team's
# channels. Pass retry=0 to opt out.
DEFAULT_RETRY = 3


def graph_get(base, endpoint, access_token, debug=False, retry=DEFAULT_RETRY):
    url = f'{base}/{endpoint.lstrip("/")}'
    try:
        return http.request('GET', url, token=access_token, retry=retry, debug=debug).json
    except (AuthExpiredError, ScopeInsufficientError):
        raise
    except _RECOVERABLE as error:
        raise error
    except OwaError as error:
        raise error


def graph_paginate(base, endpoint, access_token, debug=False, max_pages=50, retry=DEFAULT_RETRY):
    """Collect a Graph `value` collection across `@odata.nextLink` pages."""
    url = f'{base}/{endpoint.lstrip("/")}'
    try:
        return list(http.paginate(url, token=access_token, max_pages=max_pages, retry=retry, debug=debug))
    except (AuthExpiredError, ScopeInsufficientError):
        raise
    except _RECOVERABLE as error:
        raise error
    except OwaError as error:
        raise error


def graph_collect(base, endpoint, access_token, *, top=None, max_pages=50,
                  debug=False, retry=DEFAULT_RETRY):
    """Page a Graph collection, optionally capping at `top` items.

    Returns `(rows, truncated)`. With `top` set we follow `@odata.nextLink`
    only until we hold `top` items (then stop early), so a huge list isn't
    walked in full; `truncated` is True when more items remained unfetched
    (either the item cap or the page cap was reached). With `top=None` we walk
    every page up to `max_pages` and `truncated` reports the page cap.
    """
    url = f'{base}/{endpoint.lstrip("/")}'
    rows = []
    try:
        pages = http.paginate(url, token=access_token, max_pages=max_pages, retry=retry, debug=debug)
        for item in pages:
            rows.append(item)
            if top is not None and len(rows) > top:
                # We fetched one past the cap, so we know more exist.
                return rows[:top], True
        return rows, False
    except (AuthExpiredError, ScopeInsufficientError):
        raise
    except _RECOVERABLE as error:
        raise error
    except OwaError as error:
        raise error


def _page_reaches_before(messages, since_dt):
    """True once a page holds any message older than the cutoff.

    chatsvc pages newest-first and each `backwardLink` page is strictly older, so
    the first page that dips below `since_dt` is the last one worth fetching.
    """
    for message in messages:
        when = teams_mod.message_datetime(message)
        if when is not None and when < since_dt:
            return True
    return False


def _within_since(message, since_dt):
    when = teams_mod.message_datetime(message)
    return when is None or when >= since_dt


def chatsvc_messages(base, conversation_id, access_token, *, page_size=50, max_pages=20,
                     since_dt=None, debug=False, retry=DEFAULT_RETRY):
    """Fetch a conversation's chatsvc message stream, following backwardLink.

    Returns the concatenated raw `messages` (newest-first across pages), or
    None on a recoverable error. Bounded by `max_pages` so an enormous channel
    can't page forever; callers that need a time window pass a small page count
    and filter by timestamp downstream. Each page request carries `retry` so a
    429 mid-pagination is ridden through (Retry-After) instead of aborting.

    With `since_dt` (an aware datetime), pagination stops as soon as a page
    reaches past the cutoff (no point following `backwardLink` into strictly
    older pages) and the returned messages are filtered to that window;
    messages with no parseable timestamp are kept.
    """
    url = teams_mod.conversation_messages_url(base, conversation_id, page_size=page_size)
    collected = []
    pages = 0
    try:
        while url:
            resp = http.request('GET', url, token=access_token, headers=_ACCEPT_JSON,
                                 retry=retry, debug=debug)
            payload = resp.json if isinstance(resp.json, dict) else {}
            messages = payload.get('messages')
            if not isinstance(messages, list):
                break
            collected.extend(messages)
            url = (payload.get('_metadata') or {}).get('backwardLink') or ''
            pages += 1
            if since_dt is not None and _page_reaches_before(messages, since_dt):
                break
            if pages >= max_pages:
                break
        if since_dt is not None:
            collected = [m for m in collected if _within_since(m, since_dt)]
        return collected
    except (AuthExpiredError, ScopeInsufficientError):
        raise
    except _RECOVERABLE as error:
        raise error
    except OwaError as error:
        raise error


def chatsvc_post(base, conversation_id, body, access_token, debug=False, retry=DEFAULT_RETRY):
    """POST a message to a chatsvc conversation; return the parsed JSON or None.

    Verified live 2026-06-30 (crayon/emea): the `ic3` bearer carries
    `Endpoint.ReadWrite.All` and the POST returns 201 + `{OriginalArrivalTime}`.
    Auth/scope errors re-raise so the dispatcher maps them to the shared exit
    codes; other recoverable failures are re-raised too (already reported).
    """
    url = teams_mod.conversation_post_url(base, conversation_id)
    try:
        return http.request('POST', url, token=access_token, body=body,
                            headers=_ACCEPT_JSON, retry=retry, debug=debug).json
    except (AuthExpiredError, ScopeInsufficientError):
        raise
    except _RECOVERABLE as error:
        raise error
    except OwaError as error:
        raise error
