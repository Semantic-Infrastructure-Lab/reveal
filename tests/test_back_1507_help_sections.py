"""BACK-1507: help:// section navigation dead ends."""

import pytest

from reveal.adapters.help import HelpAdapter, _markdown_headings


@pytest.fixture
def adapter():
    return HelpAdapter('help://')


def test_headings_inside_fences_are_not_headings():
    lines = ['# Title', '```bash', '# 7. File history', '```', '## File History', 'body']
    assert [(i, lvl, txt) for i, lvl, txt in _markdown_headings(lines)] == [
        (0, 1, 'Title'), (4, 2, 'File History')]


def test_section_extraction_skips_fenced_comments(adapter):
    lines = ['# Guide', '```bash', '# 7. File history (50 commits)', 'reveal x', '```',
             '## File History', 'real body', '## Blame', 'other']
    assert adapter._extract_markdown_section(lines, 'File History', 'git') == '## File History\nreal body'


def test_guide_heading_slug_opens_the_section(adapter):
    result = adapter.get_element('git/file-history')
    assert result and 'error' not in result
    assert result['content'].lstrip().startswith('## File History')


def test_unknown_section_lists_only_what_exists(adapter):
    result = adapter.get_element('git/nosuch')
    assert result['error'] == 'Invalid section'
    assert 'Sections of git: none' in result['message']
    assert 'help://git/<heading-words>' in result['message']


def test_adapter_structured_sections_still_route(adapter):
    result = adapter.get_element('ast/workflows')
    assert result and 'error' not in result and result.get('type') == 'help_section'
