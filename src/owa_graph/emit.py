"""Render the equivalent `curl` or `az rest` command for a request.

Pure functions, no I/O. The dispatcher prints the rendered command to
stdout when the user passes `--curl` or `--az` and skips the actual HTTP
call. Bodies passed as `@/path/to/file` are preserved as `@file`
references rather than inlined - matches curl/az conventions and avoids
leaking large bodies into the rendered command.

shlex.quote is used on every interpolated value so the output is safe to
copy-paste into a shell. We default to multi-line backslash-continued
output because Graph URLs and OData filters get long fast.

By default the bearer token is *not* inlined: the Authorization header
renders a `$OWA_TOKEN` placeholder (double-quoted so the shell expands it
at run time) so `--curl | pbcopy` can't leak a live token into the
clipboard or shell history. Pass `include_token=True` (the `--include-token`
CLI flag) to inline the real access token.
"""
import json
import shlex

# Placeholder emitted instead of the real bearer token unless the caller
# opts in. Double-quoted (not shlex-quoted) so the shell expands the env
# var when the command is run: `export OWA_TOKEN=$(owa-piggy token ...)`.
_TOKEN_PLACEHOLDER = '$OWA_TOKEN'

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


def _auth_header_arg(label, access_token, include_token):
    """Return the already-quoted Authorization header argument.

    With `include_token`, the real bearer is inlined and shell-quoted.
    Without it, a double-quoted `$OWA_TOKEN` placeholder is emitted so the
    command stays runnable (after the user sets OWA_TOKEN) but no live
    token reaches stdout/clipboard/history. `label` is the header text up
    to the value, e.g. `'Authorization: Bearer '` (curl) or
    `'Authorization=Bearer '` (az --headers)."""
    if include_token:
        return _quote(f'{label}{access_token}')
    return f'"{label}{_TOKEN_PLACEHOLDER}"'


def render_curl(method, url, access_token, headers=None, body=None,
                body_is_file_ref=False, include_token=False):
    """Return a multi-line curl command.

    By default the bearer token is rendered as a `$OWA_TOKEN` placeholder;
    pass `include_token=True` to inline the real token.

    `body_is_file_ref=True` means `body` is a path that should be kept
    as `@<path>` so curl streams from disk - matches the `--body
    @file.json` invocation style.
    """
    parts = ['curl', '-sS', '-X', method]
    parts += ['-H', _auth_header_arg('Authorization: Bearer ', access_token, include_token)]

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
              body_is_file_ref=False, include_token=False):
    """Return a multi-line `az rest` command. Token goes via --headers,
    same as az's own examples.

    By default the bearer token is rendered as a `$OWA_TOKEN` placeholder;
    pass `include_token=True` to inline the real token."""
    parts = ['az', 'rest', '--method', method.lower(), '--uri', _quote(url)]

    parts += ['--headers']
    parts += [_auth_header_arg('Authorization=Bearer ', access_token, include_token)]
    if headers:
        parts += [_quote(f'{k}={v}') for k, v in headers.items()]

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
