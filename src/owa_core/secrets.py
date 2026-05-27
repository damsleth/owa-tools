"""Secret-shape detection and redaction helpers.

These helpers intentionally detect shapes, not validity. They are used for
defensive logging and repository scans, so false negatives are more dangerous
than occasional false positives. Keep allowlists in scanner call sites, not in
the redaction primitive.
"""
import re
from dataclasses import dataclass

REDACTION = '[redacted-secret]'
BODY_REDACTION = '[redacted-body]'

JWT_RE = re.compile(
    r'\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b'
)
REFRESH_RE = re.compile(r'\b[01]\.AQ[A-Za-z0-9._-]{12,}\b')
AUTH_HEADER_RE = re.compile(
    r'(?i)(authorization\s*[:=]\s*bearer\s+)([A-Za-z0-9._~+/=-]{8,})'
)
CLIENT_SECRET_RE = re.compile(
    r'(?i)(client_secret\s*[:=]\s*[\'"]?)([A-Za-z0-9._~+/=-]{12,})'
)
# Message-content fields per hugr CONVENTIONS.md ("Body fields named
# body, content, text"). Not a secret *shape* but message content -
# email/event/task bodies that must never reach logs or stderr (e.g. the
# debug request-body print in owa_core.http). Scrub the JSON string value
# while keeping the key so log structure stays readable. The exact-key
# match (`"content"`, not `"contentType"`) leaves harmless metadata alone.
BODY_FIELD_RE = re.compile(
    r'(?i)("(?:body|content|text|html_body|plain_body)"\s*:\s*)"[^"]*"'
)


@dataclass(frozen=True)
class SecretFinding:
    kind: str
    start: int
    end: int
    value: str


def _text(value):
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return str(value)


def find_secret_shapes(value):
    """Return secret-looking spans in value."""
    text = _text(value)
    findings = []
    for kind, pattern, group in (
        ('authorization', AUTH_HEADER_RE, 2),
        ('client_secret', CLIENT_SECRET_RE, 2),
        ('refresh_token', REFRESH_RE, 0),
        ('access_token', JWT_RE, 0),
    ):
        for match in pattern.finditer(text):
            start, end = match.span(group)
            findings.append(SecretFinding(kind, start, end, match.group(group)))
    return sorted(findings, key=lambda finding: (finding.start, finding.end))


def contains_secret(value):
    return bool(find_secret_shapes(value))


def redact(value):
    """Replace known secret-shaped substrings and message-body field
    values with stable placeholders.

    Secret shapes (JWT, refresh token, Bearer header, client_secret)
    collapse to ``REDACTION``; message-content fields (``body``,
    ``content``, ``text``, ...) collapse to ``BODY_REDACTION`` so a
    debug/error log never carries email or message content. Detection
    helpers (``find_secret_shapes``/``contains_secret``) are unchanged -
    body fields are a logging concern, not a secret-scan finding."""
    text = _text(value)
    text = AUTH_HEADER_RE.sub(r'\1' + REDACTION, text)
    text = CLIENT_SECRET_RE.sub(r'\1' + REDACTION, text)
    text = REFRESH_RE.sub(REDACTION, text)
    text = JWT_RE.sub(REDACTION, text)
    return BODY_FIELD_RE.sub(r'\1"' + BODY_REDACTION + '"', text)
