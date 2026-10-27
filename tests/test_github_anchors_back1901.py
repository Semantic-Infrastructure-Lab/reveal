"""BACK-1901: one GitHub-style anchor slugger for `--links` and L001, not two that disagree.

The expected slugs are what GitHub renders, not what reveal used to compute. Two slugifiers
had drifted (L001 turned `_` into `-`, `--links` kept it; BACK-1232 fixed hyphen runs in only one),
and neither handled emphasis, link text, a stripped trailing emoji, duplicate headings or an
explicit `<a id=...>` anchor, so a link that works on GitHub read `[BROKEN]`.
"""
import pytest

from reveal.analyzers.markdown import MarkdownAnalyzer
from reveal.rules import RuleRegistry
from reveal.utils.github_anchors import heading_anchors, heading_slug, html_anchor_ids

pytestmark = pytest.mark.component


@pytest.mark.parametrize('heading, slug', [
    ('Plain heading', 'plain-heading'),
    ('The BG77 model (`Quectel_BG77.cs`)', 'the-bg77-model-quectel_bg77cs'),
    ('Built, disabled (2026-10-14): option T behind `WATCHDOG_DIAG_CLOUD_PUBLISH`',
     'built-disabled-2026-10-14-option-t-behind-watchdog_diag_cloud_publish'),
    ('Using _underscore_ emphasis and **bold** text', 'using-underscore-emphasis-and-bold-text'),
    ('snake_case_word stays', 'snake_case_word-stays'),
    ('A [link](http://x.y/z_w) heading', 'a-link-heading'),
    ('A [ref link][label_1] heading', 'a-ref-link-heading'),
    ('CRT boundaries ... (WD-201 / WD-120)', 'crt-boundaries--wd-201--wd-120'),
    ('Em dash — here', 'em-dash--here'),
    ('Features ✨', 'features-'),
    ('Inline <b>html</b> tags', 'inline-html-tags'),
    ('Ünïcode héading', 'ünïcode-héading'),
    ('Tabs\tand  double  spaces', 'tabsand--double--spaces'),   # only ' ' becomes '-'
])
def test_heading_slug_is_githubs(heading, slug):
    assert heading_slug(heading) == slug


def test_duplicate_headings_get_numeric_suffixes_in_document_order():
    assert heading_anchors(['Dup', 'Other', 'Dup', 'Dup']) == ['dup', 'other', 'dup-1', 'dup-2']


def test_a_suffix_that_collides_with_a_real_heading_keeps_counting():
    """github-slugger: 'Dup', 'Dup 1' ('dup-1'), then a second 'Dup' cannot take 'dup-1' again."""
    assert heading_anchors(['Dup', 'Dup 1', 'Dup']) == ['dup', 'dup-1', 'dup-2']


def test_a_heading_with_no_slug_is_not_an_anchor():
    assert heading_anchors(['***', 'Real']) == ['real']


@pytest.mark.parametrize('content, ids', [
    ('| <a id="rtc-history"></a>RTC | x |', ['rtc-history']),
    ("<a name='old-style'></a>", ['old-style']),
    ('<h2 id="raw-heading">T</h2>', ['raw-heading']),
    ('<A ID="upper"></A>', ['upper']),
    ('plain text, no anchors', []),
    ('```html\n<a id="in-code"></a>\n```\n<a id="after-fence"></a>', ['after-fence']),
    ('~~~\n<a id="tilde-fence"></a>\n~~~', []),
])
def test_explicit_html_anchors(content, ids):
    assert html_anchor_ids(content) == ids


_DOC = """# Top

## The BG77 model (`Quectel_BG77.cs`)

## Using _underscore_ emphasis and **bold** text

## A [link](http://x.y/z_w) heading

## CRT boundaries ... (WD-201 / WD-120)

## Features ✨

## Dup

## Dup

| <a id="rtc-history"></a>RTC | x |

[a](#the-bg77-model-quectel_bg77cs) [b](#using-underscore-emphasis-and-bold-text)
[c](#a-link-heading) [d](#crt-boundaries--wd-201--wd-120) [e](#features-)
[f](#dup) [g](#dup-1) [h](#rtc-history)
[x1](#nope) [x2](#dup-2) [x3](#the-bg77-model-quectel-bg77cs)
"""
_BROKEN = {'#nope', '#dup-2', '#the-bg77-model-quectel-bg77cs'}


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / 'doc.md'
    path.write_text(_DOC, encoding='utf-8')
    return path


def test_links_view_marks_only_the_links_github_would_not_resolve(doc):
    analyzer = MarkdownAnalyzer(str(doc))
    broken = {link['url'] for link in analyzer._extract_links()
              if link['url'].startswith('#') and analyzer._is_broken_link(link['url'])}
    assert broken == _BROKEN


def test_l001_marks_only_the_links_github_would_not_resolve(doc):
    found = RuleRegistry.check_file(str(doc), None, doc.read_text(encoding='utf-8'), select=['L001'])
    assert {d.message.rsplit(': ', 1)[1] for d in found} == _BROKEN


def test_a_file_link_with_an_anchor_uses_the_same_rules(tmp_path, doc):
    src = tmp_path / 'src.md'
    src.write_text('[u](doc.md#using-underscore-emphasis-and-bold-text) [h](doc.md#rtc-history)'
                   ' [d](doc.md#dup-1) [n](doc.md#nope)\n', encoding='utf-8')
    analyzer = MarkdownAnalyzer(str(src))
    broken = {link['url'] for link in analyzer._extract_links() if analyzer._is_broken_link(link['url'])}
    assert broken == {'doc.md#nope'}
    found = RuleRegistry.check_file(str(src), None, src.read_text(encoding='utf-8'), select=['L001'])
    assert {d.message.rsplit(': ', 1)[1] for d in found} == {'doc.md#nope'}


def test_a_link_that_drops_the_hyphen_of_a_leading_emoji_is_broken_and_the_hint_says_why(tmp_path):
    """GitHub's id for '## 🎓 Intro' is '-intro'; '#intro' scrolls nowhere (found by comparing
    master and this change over a 500-file docs tree: 35 table-of-contents links)."""
    doc = tmp_path / 'toc.md'
    doc.write_text('[wrong](#intro) [right](#-intro)\n\n## \U0001F393 Intro\n', encoding='utf-8')
    found = RuleRegistry.check_file(str(doc), None, doc.read_text(encoding='utf-8'), select=['L001'])
    assert [d.message.rsplit(': ', 1)[1] for d in found] == ['#intro']
    assert "'## \U0001F393 Intro' is '#-intro'" in found[0].suggestion
