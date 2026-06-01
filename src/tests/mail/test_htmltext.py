"""Tests for the HTML-to-text converter used by --pretty bodies."""
from owa_mail import htmltext
from owa_mail.htmltext import html_to_text


def test_empty_and_non_string():
    assert html_to_text('') == ''
    assert html_to_text(None) == ''
    # Non-string input is coerced, not raised on.
    assert html_to_text(42) == '42'


def test_entity_unescaping():
    out = html_to_text('<p>Tom &amp; Jerry said &#39;hi&#39; &lt;here&gt;</p>')
    assert out == "Tom & Jerry said 'hi' <here>"


def test_nbsp_becomes_space():
    out = html_to_text('a&nbsp;&nbsp;b')
    assert out == 'a b'


def test_br_produces_line_break():
    out = html_to_text('line one<br>line two<br/>line three')
    assert out == 'line one\nline two\nline three'


def test_p_and_div_block_breaks():
    out = html_to_text('<div>first</div><p>second</p><div>third</div>')
    # Block elements separate content onto their own lines (blank lines
    # between blocks are allowed and capped by _normalize).
    assert [ln for ln in out.splitlines() if ln] == ['first', 'second', 'third']
    assert '\n\n\n' not in out


def test_ul_li_bullets():
    out = html_to_text('<ul><li>apple</li><li>banana</li></ul>')
    lines = [ln for ln in out.splitlines() if ln]
    assert lines == ['- apple', '- banana']


def test_table_cells_separated_not_glued():
    # Adjacent cells on a row must not concatenate ("AB"); they get a
    # space separator. Rows still break onto separate lines.
    out = html_to_text('<table><tr><td>A</td><td>B</td></tr>'
                       '<tr><td>C</td><td>D</td></tr></table>')
    lines = [ln for ln in out.splitlines() if ln]
    assert lines == ['A B', 'C D']


def test_script_and_style_removed():
    html = (
        '<style>.x{color:red}</style>'
        '<p>visible</p>'
        '<script>alert("nope");</script>'
    )
    out = html_to_text(html)
    assert out == 'visible'
    assert 'color' not in out
    assert 'alert' not in out


def test_whitespace_collapsing():
    out = html_to_text('<span>too    many     spaces\n\n\there</span>')
    assert out == 'too many spaces here'


def test_blank_line_runs_collapsed():
    html = '<p>a</p><p></p><p></p><p></p><p>b</p>'
    out = html_to_text(html)
    # Never more than one blank line between content.
    assert '\n\n\n' not in out
    assert out.splitlines()[0] == 'a'
    assert out.splitlines()[-1] == 'b'


def test_links_become_numbered_footnotes():
    out = html_to_text('Click <a href="https://example.com/track?x=1">here</a> now')
    # Visible text keeps a [n] marker; the URL lands in a trailing section.
    assert out == 'Click here [1] now\n\nLinks:\n[1] https://example.com/track?x=1'


def test_links_dropped_when_footnotes_disabled():
    out = html_to_text(
        'Click <a href="https://example.com/track?x=1">here</a> now',
        link_footnotes=False,
    )
    assert out == 'Click here now'
    assert 'example.com' not in out


def test_duplicate_urls_share_one_footnote():
    out = html_to_text(
        '<a href="https://x.test/a">one</a> and '
        '<a href="https://x.test/a">again</a>'
    )
    assert 'one [1]' in out
    assert 'again [1]' in out
    # The shared URL is listed exactly once.
    assert out.count('[1] https://x.test/a') == 1
    assert '[2]' not in out


def test_distinct_urls_get_sequential_footnotes():
    out = html_to_text(
        '<a href="https://x.test/a">a</a> <a href="https://x.test/b">b</a>'
    )
    section = out.split('Links:\n', 1)[1]
    assert section == '[1] https://x.test/a\n[2] https://x.test/b'


def test_non_web_anchors_not_footnoted():
    out = html_to_text(
        'mail <a href="mailto:x@y.test">x</a> '
        'jump <a href="#section">s</a> '
        'js <a href="javascript:void(0)">j</a> '
        'empty <a href="">e</a> '
        'bare <a>b</a>'
    )
    assert 'Links:' not in out
    assert '[1]' not in out
    # Visible anchor text is still kept.
    for word in ('mail x', 'jump s', 'js j', 'empty e', 'bare b'):
        assert word in out


def test_anchor_without_text_still_recovers_url():
    out = html_to_text('<a href="https://x.test/login"></a>')
    assert '[1]' in out
    assert out.endswith('Links:\n[1] https://x.test/login')


def test_fallback_path_has_no_footnotes(monkeypatch):
    def boom(self, data):
        raise RuntimeError('parser exploded')

    monkeypatch.setattr(htmltext._TextExtractor, 'feed', boom)
    out = html_to_text('Click <a href="https://example.com">here</a>')
    assert 'Links:' not in out
    assert 'here' in out


def test_headings_break():
    out = html_to_text('<h1>Title</h1><p>Body text</p>')
    lines = [ln for ln in out.splitlines() if ln]
    assert lines == ['Title', 'Body text']


def test_malformed_html_does_not_raise():
    # Unclosed tags, stray brackets, broken entities - must not raise.
    for bad in (
        '<p>unclosed <b>bold <i>italic',
        '<<>> &notreal; <p',
        '<div><span>text</div></span>',
        '3 < 5 and 5 > 2',
    ):
        out = html_to_text(bad)
        assert isinstance(out, str)


def test_strips_leading_trailing_whitespace():
    out = html_to_text('<p>   padded   </p>')
    assert out == 'padded'


def test_table_rows_break():
    out = html_to_text('<table><tr>a</tr><tr>b</tr></table>')
    lines = [ln for ln in out.splitlines() if ln]
    assert lines == ['a', 'b']


def test_nested_markup_inside_script_dropped():
    # Tags nested inside a skipped element (incl. self-closing and block
    # tags) must stay suppressed until the skip element closes.
    # <head> is parsed normally (unlike <script>, whose body is raw text),
    # so its nested start/self-closing/end tags exercise the skip-depth
    # guards while still being suppressed from output.
    html = (
        'before'
        '<head><p>x</p><br/><div>y</div></head>'
        'after'
    )
    out = html_to_text(html)
    assert 'x' not in out
    assert 'y' not in out
    assert 'before' in out
    assert 'after' in out


def test_self_closing_block_and_hr():
    out = html_to_text('a<hr/>b<p/>c')
    lines = [ln for ln in out.splitlines() if ln]
    assert lines == ['a', 'b', 'c']


def test_self_closing_skip_tag():
    # A self-closing skip tag (e.g. <script/>) is a no-op, not a break.
    out = html_to_text('a<script/>b')
    assert out == 'ab'


def test_fallback_when_parser_raises(monkeypatch):
    # If the parser blows up for any reason, fall back to a regex strip
    # plus entity unescape rather than raising.
    def boom(self, data):
        raise RuntimeError('parser exploded')

    monkeypatch.setattr(htmltext._TextExtractor, 'feed', boom)
    out = html_to_text('<p>Tom &amp; Jerry</p>')
    assert 'Tom & Jerry' in out
    assert '<p>' not in out
