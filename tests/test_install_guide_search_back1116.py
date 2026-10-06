"""BACK-1116: the install guide (optional extras, network requirements) is findable
through reveal's own discovery path, help://search, and readable at help://install.

Before this, INSTALL.md lived outside the bundled reveal/docs corpus, so a search for
'pygit2', 'optional-dependencies' or 'tree-sitter-language-pack download' found nothing
and 'extras'/'air-gapped' matched only a passing sentence inside help://agent.
"""

import re
from pathlib import Path

import pytest

from reveal.adapters.help import HelpAdapter

pytestmark = pytest.mark.component


def _guide_topics(term):
    result = HelpAdapter().get_element(f'search?search={term}')
    assert result['type'] == 'help_search'
    return [h['topic'] for h in result['hits'] if h['type'] == 'guide']


@pytest.mark.parametrize('term', [
    'extras',
    'optional-dependencies',
    'pygit2',
    'air-gapped',
    'network',
    'tree-sitter-language-pack download',
])
def test_search_finds_the_install_guide(term):
    assert 'install' in _guide_topics(term)


def test_extras_search_ranks_the_install_guide_first():
    """A guide whose own topic/description names the term outranks a passing mention."""
    assert _guide_topics('extras')[0] == 'install'


def test_nonsense_term_finds_nothing():
    """Negative control: the guide is matched by content, not returned for everything."""
    result = HelpAdapter().get_element('search?search=zzqxvnonsensetermqq')
    assert result['count'] == 0


def _pyproject_extras():
    """Extras names from [project.optional-dependencies] (no tomllib on Python 3.10)."""
    text = (Path(__file__).resolve().parent.parent / 'pyproject.toml').read_text(encoding='utf-8')
    section = text.split('[project.optional-dependencies]', 1)[1].split('\n[', 1)[0]
    return re.findall(r'^(\w+)\s*=\s*\[', section, flags=re.MULTILINE)


def test_install_topic_is_readable_and_lists_every_pyproject_extra():
    extras = _pyproject_extras()
    assert {'git', 'database', 'mcp'} <= set(extras)  # the parser found the table
    result = HelpAdapter().get_element('install')
    assert result is not None
    content = result.get('content') or ''
    missing = [name for name in extras if f'reveal-cli[{name}]' not in content]
    assert not missing, f'extras absent from help://install: {missing}'
