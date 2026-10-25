"""Heading anchors resolve the way GitHub renders them.

GitHub lowercases the heading, drops punctuation (keeping word characters, underscores and
hyphens), then turns EACH space into its own hyphen. "Onboarding & Exploration" is therefore
`#onboarding--exploration` and `foo_bar` stays `foo_bar`. The analyzer used to collapse runs of
spaces, underscores and hyphens into one hyphen, so a link that works on GitHub was reported
broken and the single-hyphen spelling that GitHub does not resolve passed.
"""

import pytest

from reveal.analyzers.markdown import MarkdownAnalyzer

pytestmark = pytest.mark.component

TARGET = '# Top\n\n## Onboarding & Exploration\n\n## Snake_case name\n\n## A — B\n\n## Plain heading\n'


def _broken(tmp_path, anchor):
    """Whether the analyzer flags a same-document `#anchor` link as broken."""
    path = tmp_path / 'b.md'
    path.write_text(TARGET + f'\n[x](#{anchor})\n', encoding='utf-8')
    links = MarkdownAnalyzer(str(path)).get_structure(extract_links=True)['links']
    (link,) = [l for l in links if l['url'] == f'#{anchor}']
    return link['broken']


@pytest.mark.parametrize('anchor', [
    'onboarding--exploration',   # ampersand dropped, both spaces kept
    'snake_case-name',           # underscore survives
    'a--b',                      # em dash dropped, both spaces kept
    'plain-heading',             # control: the ordinary case is unchanged
])
def test_github_spelling_of_an_anchor_verifies_clean(tmp_path, anchor):
    assert _broken(tmp_path, anchor) is False


@pytest.mark.parametrize('anchor', [
    'onboarding-exploration',    # collapsed spelling: GitHub does not resolve it
    'snake-case-name',
    'a-b',
])
def test_collapsed_spelling_is_reported_broken(tmp_path, anchor):
    assert _broken(tmp_path, anchor) is True
