"""Render the equivalent `curl` or `az rest` command for a request.

Pure functions, no I/O. The dispatcher prints the rendered command to
stdout when the user passes `--curl` or `--az` and skips the actual HTTP
call. Bodies passed as `@/path/to/file` are preserved as `@file`
references rather than inlined - matches curl/az conventions and avoids
leaking large bodies into the rendered command.

shlex.quote is used on every interpolated value so the output is safe to
copy-paste into a shell. We default to multi-line backslash-continued
output because Graph URLs and OData filters get long fast.
"""
import json
import shlex

# Tokens that introduce a flag (and usually take a value). Used by
# _join_continuation to decide where to break lines.
_FLAG_TOKENS = frozenset({
    '-s', '-sS', '-X', '-H',
    '--data', '--method', '--uri', '--headers', '--body',
})


def _quote(s):
    return shlex.quote(s)


def _serialize_body(body):
    """Return (literal_string, is_json) for a body value.

    Dicts/lists are JSON-encoded compact; bytes are decoded; strings
    pass through. Returns None if body is None.
    """
    if body is None:
        return None
    if isinstance(body, (dict, list)):
        return json.dumps(body, ensure_ascii=False, separators=(',', ':'))
    if isinstance(body, (bytes, bytearray)):
        return bytes(body).decode('utf-8', errors='replace')
    return str(body)


def render_curl(method, url, access_token, headers=None, body=None,
                body_is_file_ref=False):
    """Return a multi-line curl command. The bearer token is inlined.

    `body_is_file_ref=True` means `body` is a path that should be kept
    as `@<path>` so curl streams from disk - matches the `--body
    @file.json` invocation style.
    """
    parts = ['curl', '-sS', '-X', method]
    parts += ['-H', _quote(f'Authorization: Bearer {access_token}')]

    needs_content_type = body is not None
    if needs_content_type:
        parts += ['-H', _quote('Content-Type: application/json')]
    if headers:
        for k, v in headers.items():
            parts += ['-H', _quote(f'{k}: {v}')]

    if body is not None:
        if body_is_file_ref:
            parts += ['--data', _quote(f'@{body}')]
        else:
            parts += ['--data', _quote(_serialize_body(body))]

    parts += [_quote(url)]
    return _join_continuation(parts)


def render_az(method, url, access_token, headers=None, body=None,
              body_is_file_ref=False):
    """Return a multi-line `az rest` command. Token goes via --headers,
    same as az's own examples."""
    parts = ['az', 'rest', '--method', method.lower(), '--uri', _quote(url)]

    hdr_pairs = [f'Authorization=Bearer {access_token}']
    if headers:
        for k, v in headers.items():
            hdr_pairs.append(f'{k}={v}')
    parts += ['--headers']
    parts += [_quote(p) for p in hdr_pairs]

    if body is not None:
        if body_is_file_ref:
            parts += ['--body', _quote(f'@{body}')]
        else:
            parts += ['--body', _quote(_serialize_body(body))]
    return _join_continuation(parts)


def _join_continuation(parts):
    """Pretty-print a long argv as a multi-line command.

    Strategy: keep the program name, any leading non-flag positional
    tokens, and the *first* flag (with its value) on line 1. Each
    subsequent flag (with its value) goes on its own continuation line.
    Trailing positional tokens (e.g. the curl URL) attach to whatever
    chunk they follow.
    """
    if len(parts) <= 4:
        return ' '.join(parts)

    chunks = []
    current = []
    seen_first_flag = False
    i = 0
    while i < len(parts):
        tok = parts[i]
        if tok in _FLAG_TOKENS:
            if seen_first_flag:
                if current:
                    chunks.append(current)
                current = [tok]
            else:
                current.append(tok)
                seen_first_flag = True
            # Consume the value if next token is not itself a flag.
            if i + 1 < len(parts) and parts[i + 1] not in _FLAG_TOKENS:
                current.append(parts[i + 1])
                i += 2
                continue
            i += 1
            continue
        current.append(tok)
        i += 1
    if current:
        chunks.append(current)

    if len(chunks) <= 1:
        return ' '.join(parts)
    head = ' '.join(chunks[0])
    rest = ['  ' + ' '.join(c) for c in chunks[1:]]
    return ' \\\n'.join([head] + rest)
