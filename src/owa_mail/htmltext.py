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


def _link_href(attrs):
    """Pull a footnote-worthy href out of an <a> tag's attrs.

    Returns the http(s) URL or '' for anchors we don't footnote
    (mailto:, in-page #fragments, javascript:, empty, or non-web schemes).
    """
    for name, value in attrs:
        if name.lower() != 'href':
            continue
        if not value:
            return ''
        url = value.strip()
        if url[:7].lower() == 'http://' or url[:8].lower() == 'https://':
            return url
        return ''
    return ''


class _TextExtractor(HTMLParser):
    """Accumulate visible text, inserting newlines for block elements.

    `convert_charrefs=True` (the default on modern Python) means the parser
    resolves entities for us before calling `handle_data`, so a separate
    unescape pass is belt-and-suspenders rather than load-bearing.

    Anchor hrefs are collected as numbered footnotes: each unique http(s)
    URL gets a stable number, a ` [n]` marker is emitted after the anchor's
    visible text, and `links` ends up as an ordered list of `(n, url)`
    pairs for the caller to render. This is what keeps a "Sign in" button's
    URL recoverable instead of silently dropped.
    """

    def __init__(self, footnotes=True):
        super().__init__(convert_charrefs=True)
        self._parts = []
        self._skip_depth = 0
        self._footnotes = footnotes
        # url -> footnote number, assigned in first-seen order.
        self._link_numbers = {}
        self.links = []
        # Stack of pending hrefs, one per open <a>; '' when the anchor is
        # not footnote-worthy. A stack handles (rare) nested anchors.
        self._href_stack = []

    def _footnote(self, url):
        """Return the footnote number for `url`, assigning a new one the
        first time the URL is seen and recording it on `self.links`."""
        n = self._link_numbers.get(url)
        if n is None:
            n = len(self._link_numbers) + 1
            self._link_numbers[url] = n
            self.links.append((n, url))
        return n

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
        elif tag == 'a':
            self._href_stack.append(_link_href(attrs))
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
        if tag == 'a' and self._href_stack:
            url = self._href_stack.pop()
            if url and self._footnotes:
                self._parts.append(f' [{self._footnote(url)}]')
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


def _links_section(links):
    """Render collected `(n, url)` pairs as a trailing footnote block."""
    if not links:
        return ''
    lines = '\n'.join(f'[{n}] {url}' for n, url in links)
    return f'\n\nLinks:\n{lines}'


def html_to_text(html, *, link_footnotes=True):
    """Flatten an HTML fragment to readable plain text.

    Robust to malformed markup: any parser error falls back to a regex
    tag-strip plus entity unescape rather than raising.

    By default (`link_footnotes=True`), anchor URLs are preserved as
    numbered footnotes: each link's visible text is followed by a ` [n]`
    marker and a trailing `Links:` section lists the URLs. This keeps prose
    readable while making every URL - login links, confirmations - recoverable.
    Pass `link_footnotes=False` to drop URLs entirely (text only). The
    malformed-input fallback never has footnotes, since the regex strip
    can't recover anchor structure.
    """
    if not html:
        return ''
    if not isinstance(html, str):
        html = str(html)
    parser = _TextExtractor(footnotes=link_footnotes)
    try:
        parser.feed(html)
        parser.close()
        text = parser.text()
        links = parser.links
    except Exception:
        # HTMLParser is lenient, but never let bad input crash rendering.
        import html as _html_mod
        text = _html_mod.unescape(re.sub(r'<[^>]*>', ' ', html))
        links = []
    body = _normalize(text)
    if link_footnotes and links:
        return body + _links_section(links)
    return body
