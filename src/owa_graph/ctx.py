"""Request context handed to resource group handlers.

A resource handler shouldn't have to know how to build a Graph URL,
mint a token, stream paginated results, or pretty-print. It declares
the request shape; ``RequestContext`` does the work.

The point of pulling this out of ``cli.cmd_request`` is symmetry: 14
resource groups and 100 shortcuts all need exactly the same plumbing.
We lock the contract here once.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Tuple

from . import api as api_mod
from . import format as format_mod

QueryPairs = Sequence[Tuple[str, str]]


@dataclass
class RequestContext:
    """All the state a resource handler needs to talk to Graph.

    Resource handlers receive an instance of this from the dispatcher;
    they call :meth:`get`/:meth:`post`/:meth:`patch`/:meth:`delete` and
    return the handler's exit code (0 or 1). The context owns output
    formatting so each handler stays at 5-15 LOC.
    """
    config: Mapping[str, Any]
    access_token: str
    api_base: str
    debug: bool = False
    pretty: bool = False
    ndjson: bool = False
    retry: bool = False
    extra_headers: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Verb wrappers
    # ------------------------------------------------------------------

    def get(self, path: str, *, query: Optional[QueryPairs] = None,
            headers: Optional[Mapping[str, str]] = None,
            pretty_shape: Optional[str] = None,
            paginate: bool = False) -> int:
        url = api_mod.build_url(self.api_base, path, query)
        merged = self._merge_headers(headers)
        if paginate:
            return self._emit_paginated(url, merged, pretty_shape)
        result = api_mod.api_request(
            'GET', '', url, self.access_token,
            extra_headers=merged, debug=self.debug, retry=self.retry,
        )
        return self._emit(result, pretty_shape)

    def post(self, path: str, body: Any, *,
             headers: Optional[Mapping[str, str]] = None,
             pretty_shape: Optional[str] = None) -> int:
        return self._mutating('POST', path, body, headers, pretty_shape)

    def patch(self, path: str, body: Any, *,
              headers: Optional[Mapping[str, str]] = None,
              pretty_shape: Optional[str] = None) -> int:
        return self._mutating('PATCH', path, body, headers, pretty_shape)

    def put(self, path: str, body: Any, *,
            headers: Optional[Mapping[str, str]] = None,
            pretty_shape: Optional[str] = None) -> int:
        return self._mutating('PUT', path, body, headers, pretty_shape)

    def delete(self, path: str, *,
               headers: Optional[Mapping[str, str]] = None) -> int:
        url = api_mod.build_url(self.api_base, path)
        merged = self._merge_headers(headers)
        result = api_mod.api_request(
            'DELETE', '', url, self.access_token,
            extra_headers=merged, debug=self.debug, retry=self.retry,
        )
        if result is None:
            return 1
        # 204 No Content surfaces as ``{}``. Don't print anything when
        # there's no body - delete is intent-driven, the caller can
        # check the exit code.
        if result == {}:
            return 0
        return self._emit(result, None)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _mutating(self, method, path, body, headers, pretty_shape):
        url = api_mod.build_url(self.api_base, path)
        merged = self._merge_headers(headers)
        result = api_mod.api_request(
            method, '', url, self.access_token,
            body=body, extra_headers=merged,
            debug=self.debug, retry=self.retry,
        )
        return self._emit(result, pretty_shape)

    def _merge_headers(self, headers):
        if not headers:
            return dict(self.extra_headers) if self.extra_headers else None
        merged = dict(self.extra_headers) if self.extra_headers else {}
        merged.update(headers)
        return merged

    def _emit(self, result, pretty_shape):
        if result is None:
            return 1
        if self.ndjson:
            if isinstance(result, dict) and isinstance(result.get('value'), list):
                for item in result['value']:
                    print(json.dumps(item, ensure_ascii=False))
            else:
                print(json.dumps(result, ensure_ascii=False))
            return 0
        if self.pretty:
            print(format_mod.format_pretty(result))
        else:
            print(json.dumps(result, ensure_ascii=False))
        return 0

    def _emit_paginated(self, url, headers, pretty_shape):
        items_iter = api_mod.paginate(
            'GET', url, self.access_token,
            extra_headers=headers, debug=self.debug, retry=self.retry,
        )
        if self.ndjson:
            for item in items_iter:
                print(json.dumps(item, ensure_ascii=False))
            return 0
        items = list(items_iter)
        payload = {'value': items}
        if self.pretty:
            print(format_mod.format_pretty(payload))
        else:
            print(json.dumps(payload, ensure_ascii=False))
        return 0
