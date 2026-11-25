"""``help://schemas/X``'s "Available:" list names no retired scheme (BACK-2804).

An unknown schema topic teaches the schemes to use instead. It read every registered adapter with a schema, so it named
eight schemes the RETIREMENTS table retires (architecture, classify, depends, deps, hotspots, stats, testability,
trace): a reader who followed it learned a spelling that notes now and exits 2 at the cut. Hints and listings read
``current_schemes()`` (BACK-2532), and so does this one. A removed scheme's own topic is its row's text
(``tests/test_removed_help_topic_back2771.py``).

Siblings: a live schema answers, and a retired scheme that still answers (the note stage) keeps its schema page.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.cli.invocation import RETIREMENTS

RETIRED = sorted(key.split(':', 1)[1] for key in RETIREMENTS if key.startswith('scheme:'))


def _available(message):
    """The scheme names after "Available: " in the teaching sentence."""
    return message.split('Available: ', 1)[1].split(', ')


def test_the_unknown_schema_topic_lists_no_retired_scheme():
    result = _run_reveal_direct('help://schemas/nosuchadapter', '--format', 'json')
    assert result.returncode == 2
    page = json.loads(result.stdout)
    listed = set(page['available_adapters'])
    assert {'ast', 'calls', 'imports', 'metrics', 'patches'} <= listed  # the replacements are taught
    assert listed.isdisjoint(RETIRED), sorted(listed & set(RETIRED))
    assert set(_available(page['error'])) == listed


def test_the_text_answer_says_the_same_list():
    result = _run_reveal_direct('help://schemas/nosuchadapter')
    assert result.returncode == 2
    [line] = [line for line in result.stderr.splitlines() if 'Available: ' in line]
    assert set(_available(line)).isdisjoint(RETIRED), line
    assert 'metrics' in _available(line)


def test_the_api_raises_with_the_same_list():
    from reveal import api
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError) as raised:
        api.query('help://schemas/nosuchadapter')
    assert set(_available(str(raised.value))).isdisjoint(RETIRED), str(raised.value)


@pytest.mark.parametrize('scheme', ['ast', 'stats'])
def test_a_schema_that_exists_still_answers(scheme):
    """``ast`` is live; ``stats`` is retired at the note stage and still answers its schema until the cut."""
    result = _run_reveal_direct(f'help://schemas/{scheme}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['adapter'] == scheme
