"""HTML-to-text rendering for --pretty mail bodies.

Microsoft Graph returns message bodies with `contentType: "html"` very
often. Printing that markup verbatim in a terminal is unreadable, so we
flatten it to plain text for the human-facing `--pretty` path only. The
JSON path keeps the raw body untouched.

Stdlib only: `html.parser.HTMLParser` does the tokenising and
`html.unescape` handles any entities the parser hands us as already-text.
This is a pragmatic flattener, not a browser: it drops `<script>`/`<style>`
content, turns block-level elements into line breaks, bullets list items,
separates table cells, collapses whitespace, and never raises on malformed
input. Known limitation: `<pre>` content is whitespace-collapsed like any
other text rather than preserved verbatim, so pre-formatted code/tables in
a mail body lose their original spacing in `--pretty`.
"""
import re
from html.parser import HTMLParser

# Tags whose start/end should force a line break in the output.
_BLOCK_TAGS = frozenset({
    'p', 'div', 'section', 'article', 'header', 'footer', 'aside', 'nav',
    'ul', 'ol', 'li', 'table', 'tr', 'thead', 'tbody', 'tfoot',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'hr',
    'figure', 'figcaption', 'address', 'fieldset', 'form', 'dl', 'dt', 'dd',
})

# Tags whose text content we drop entirely.
_SKIP_TAGS = frozenset({'script', 'style', 'head', 'title', 'noscript'})

# Table cells aren't block-level (no line break), but adjacent cells on a
# row must not glue together ("AB"); separate them with a tab, which the
# whitespace pass folds to a single space.
_CELL_TAGS = frozenset({'td', 'th'})

_WS_RE = re.compile(r'[ \t\f\v]+')
_BLANKLINES_RE = re.compile(r'\n{3,}')


class _TextExtractor(HTMLParser):
    """Accumulate visible text, inserting newlines for block elements.

    `convert_charrefs=True` (the default on modern Python) means the parser
    resolves entities for us before calling `handle_data`, so a separate
    unescape pass is belt-and-suspenders rather than load-bearing.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == 'br':
            self._parts.append('\n')
        elif tag == 'li':
            self._parts.append('\n- ')
        elif tag in _CELL_TAGS:
            self._parts.append('\t')
        elif tag in _BLOCK_TAGS:
            self._parts.append('\n')

    def handle_startendtag(self, tag, attrs):
        # Self-closing forms like <br/> or <hr/>.
        if tag in _SKIP_TAGS:
            return
        if self._skip_depth:
            return
        if tag in ('br', 'hr') or tag in _BLOCK_TAGS:
            self._parts.append('\n')

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in _BLOCK_TAGS:
            self._parts.append('\n')

    def handle_data(self, data):
        if self._skip_depth:
            return
        # Treat &nbsp; (U+00A0) as a normal space. Newlines inside text
        # nodes are insignificant in HTML source, so fold them to spaces;
        # the only meaningful line breaks are the ones we inject for tags.
        text = data.replace('\xa0', ' ')
        text = _WS_RE.sub(' ', text.replace('\r', ' ').replace('\n', ' '))
        if text:
            self._parts.append(text)

    def text(self):
        return ''.join(self._parts)


def _normalize(raw):
    """Collapse whitespace and blank-line runs into clean terminal text."""
    # Per-line: strip trailing/leading horizontal whitespace and collapse
    # interior runs. Keep the line structure that block tags produced.
    lines = []
    for line in raw.split('\n'):
        collapsed = _WS_RE.sub(' ', line).strip()
        lines.append(collapsed)
    text = '\n'.join(lines)
    # At most two consecutive newlines (one blank line) between blocks.
    text = _BLANKLINES_RE.sub('\n\n', text)
    return text.strip()


def html_to_text(html):
    """Flatten an HTML fragment to readable plain text.

    Robust to malformed markup: any parser error falls back to a regex
    tag-strip plus entity unescape rather than raising. Links keep their
    visible text only (no bracketed URL); inline anchors are common in
    signatures and tracking and bracketed URLs add more noise than value.
    """
    if not html:
        return ''
    if not isinstance(html, str):
        html = str(html)
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
        text = parser.text()
    except Exception:
        # HTMLParser is lenient, but never let bad input crash rendering.
        import html as _html_mod
        text = _html_mod.unescape(re.sub(r'<[^>]*>', ' ', html))
    return _normalize(text)
