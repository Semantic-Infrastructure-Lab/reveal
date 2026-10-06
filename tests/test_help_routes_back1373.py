"""help:// topic routing is one table, and its names are the discovery topics (BACK-1373).

_get_element_impl was a 146-line branch chain (complexity 37). It now looks a topic
up in _fixed_topic_routes(), then _prefix_topic_routes(), then the section and
bare-name fallbacks. suggest_topics() derives its discovery names from the same
table instead of a second hand-typed tuple.
"""

import pytest

from reveal.adapters.help import HelpAdapter


@pytest.fixture(scope='module')
def adapter():
    return HelpAdapter('')


def test_every_fixed_route_resolves(adapter):
    for topic in adapter._fixed_topic_routes():
        result = adapter.get_element(topic)
        assert isinstance(result, dict), topic
        assert result.get('type'), topic


def test_fixed_route_wins_over_same_named_guide(adapter):
    # 'anti-patterns' is also a STATIC_HELP alias of AGENT_HELP.md; the bounded
    # section page must win, not the full guide.
    assert 'anti-patterns' in adapter.help_topics
    assert adapter.get_element('anti-patterns')['type'] == 'static_help'
    assert adapter._load_static_help('anti-patterns')['type'] == 'static_guide'


def test_prefix_routes_receive_the_remainder(adapter):
    assert adapter.get_element('search/limit')['query'] == 'limit'
    assert adapter.get_element('search?search=git+history')['query'] == 'git history'
    assert adapter.get_element('examples/security')['type'] != 'query_recipes_index'
    assert adapter.get_element('schemas/git') is not None


def test_unknown_topics_still_return_none(adapter):
    assert adapter.get_element('nosuchtopic') is None
    assert adapter.get_element('nosuch/section') is None


def test_every_bare_route_is_a_suggestion_candidate(adapter):
    for topic in adapter._fixed_topic_routes():
        if '/' in topic:
            continue
        typo = topic[:-1]
        assert topic in adapter.suggest_topics(typo, n=10), topic


def test_suggestions_follow_the_table(adapter, monkeypatch):
    # Negative control: a route added to the table becomes suggestable with no
    # second list to update (the old _DISCOVERY_TOPICS tuple would not have known it).
    assert 'zebrapage' not in adapter.suggest_topics('zebrapag')
    routes = adapter._fixed_topic_routes()
    monkeypatch.setattr(adapter, '_fixed_topic_routes',
                        lambda: {**routes, 'zebrapage': adapter._get_quick_help})
    assert 'zebrapage' in adapter.suggest_topics('zebrapag')
