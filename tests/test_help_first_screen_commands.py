"""BACK-1613: a large guide's first screen (help://<topic> without /full) must show a
command to run when the guide has one. help://diff opened on a 17-entry table of
contents and an overview; help://claude, ssl, env and stats had no command either.
"""

import pytest

from reveal.adapters.help import HelpAdapter, _shows_command, _without_contents_section

_ADAPTER = HelpAdapter('help://')


def _first_screens():
    for topic in sorted(_ADAPTER.help_topics):
        full = _ADAPTER._load_static_help(topic, full=True)
        short = _ADAPTER._load_static_help(topic)
        if not full or not short or 'error' in full or full['content'] == short['content']:
            continue
        yield pytest.param(full['content'], short['content'], id=topic)


@pytest.mark.parametrize('full, short', list(_first_screens()))
def test_first_screen_shows_a_command_when_the_guide_has_one(full, short):
    if _shows_command(full.splitlines()):
        assert _shows_command(short.split('\n── ', 1)[0].splitlines())


def test_diff_first_screen_skips_its_contents_and_reaches_quick_start():
    content = _ADAPTER._load_static_help('diff')['content']
    assert '## Table of Contents' not in content
    assert 'reveal diff://' in content.split('\n── ', 1)[0]


def test_contents_section_is_dropped_only_at_level_two():
    lines = ['# G', '## Table of Contents', '1. [A](#a)', '## A', 'body', '### Contents', 'x']
    assert _without_contents_section(lines) == ['# G', '## A', 'body', '### Contents', 'x']


def _scheme_topics():
    from reveal.adapters.base import list_supported_schemes
    return sorted(list_supported_schemes())


@pytest.mark.parametrize('scheme', _scheme_topics())
def test_help_topic_for_a_scheme_is_about_that_scheme(scheme):
    """BACK-1611 item 5: help://<scheme> opens on its own scheme, not a neighbour's or an error."""
    import json
    result = _ADAPTER.get_element(scheme)
    assert result and 'error' not in result, result
    opening = json.dumps(result, default=str)[:3000].lower()
    assert scheme.lower() in opening, f'help://{scheme} opens on something else: {opening[:200]}'
