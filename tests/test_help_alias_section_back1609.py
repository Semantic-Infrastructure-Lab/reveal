"""BACK-1609: help://pack and help://health opened on the wrong section.

They are aliases of SUBCOMMANDS_GUIDE.md, whose first-screen cut shows the
dev and review sections; the pack and health sections were reachable only via
/full. An alias topic whose guide has a ``## reveal <topic>`` heading now
opens on that section.
"""

import pytest

from reveal.adapters.help import HelpAdapter


@pytest.fixture
def adapter():
    return HelpAdapter('help://')


@pytest.mark.parametrize('topic', ['pack', 'health', 'review', 'dev'])
def test_alias_opens_on_its_own_section(adapter, topic):
    content = adapter.get_element(topic)['content']
    assert content.lstrip().startswith(f'## reveal {topic} ')
    others = {'pack', 'health', 'review', 'dev'} - {topic}
    assert not any(f'## reveal {o} ' in content for o in others)
    assert f'help://{topic}/full' in content
    assert 'help://subcommands' in content


def test_canonical_topic_keeps_the_first_screen_cut(adapter):
    content = adapter.get_element('subcommands')['content']
    assert '## reveal dev ' in content
    assert '## reveal pack ' not in content
    assert 'Full guide: reveal help://subcommands/full' in content


def test_full_still_returns_the_whole_guide(adapter):
    content = adapter.get_element('pack/full')['content']
    assert '## reveal dev ' in content and '## reveal pack ' in content
