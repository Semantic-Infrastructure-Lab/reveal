"""The rule-line pointer can name a parent object that holds several rule sentences (BACK-2599, ruled for overview).

Overview keeps its rules in ``map.rules`` (the edge rule, each section's, the component order), ``map.entry_point_filter``
and ``diagnostic_budget``. Naming every leaf made the pointer itself ~270 bytes, so a parent object whose fields hold
sentences is a rule location too: the pointer names the parent, and a detailed view prints each sentence under it in
order (an object with a ``text`` sentence, like ``edge_rule``, contributes that one; its other strings are facts).
Strings and lists of strings are unchanged (``tests/test_rule_text_lines_lists_back2616.py``).
"""
from reveal.utils.warning_render import rule_text_lines

RESULT = {'map': {'rules': {'edge_rule': {'text': 'edge rule', 'lazy': True, 'tests': 'included'},
                            'edge_rule_sections': {'cycles': {'text': 'cycle rule'}},
                            'component_order': 'order rule'},
                  'counts': {'files': 3, 'capped': False}, 'empty': {}},
          'scope': {'counting_rule': 'census rule'}}


def test_a_parent_object_of_sentences_is_one_rule_location():
    assert rule_text_lines(RESULT, fields=('scope.counting_rule', 'map.rules'), standing_types=frozenset()) == \
        ['Rules: --format json (scope.counting_rule, map.rules)']


def test_a_detailed_view_prints_every_sentence_under_the_parent_in_order():
    lines = rule_text_lines(RESULT, fields=('map.rules',), standing_types=frozenset(), detail=True,
                            detail_supported=True)
    assert lines == ['Rules: --format json (map.rules); --detail for full text', 'edge rule', 'cycle rule', 'order rule']


def test_an_object_without_sentences_is_no_location():
    assert rule_text_lines(RESULT, fields=('map.counts', 'map.empty'), standing_types=frozenset()) == []
