"""The rule-line budget's pointer reaches a standing-caveat list too (BACK-2599 helper, adopted by git in BACK-2616).

Git ownership keeps its standing caveats in ``_meta.known_limits`` (a list of sentences). ``rule_text_lines`` pointed
only at string fields, so a noun keeping its caveats as a list could not adopt the one-line pointer. A non-empty list of
strings is a rule location like a string: the pointer names it, and a detailed view prints each sentence.
"""
from reveal.utils.warning_render import rule_text_lines

RESULT = {'_meta': {'known_limits': ['commit-share, not line-ownership', 'merges excluded by default']},
          'walk_rule': {'text': 'one rule'}, 'empty': []}


def test_a_list_of_sentences_is_a_rule_location():
    assert rule_text_lines(RESULT, fields=('_meta.known_limits',), standing_types=frozenset()) == \
        ['Rules: --format json (_meta.known_limits)']


def test_a_detailed_view_prints_each_sentence_after_the_pointer():
    lines = rule_text_lines(RESULT, fields=('walk_rule.text', '_meta.known_limits'), standing_types=frozenset(),
                            detail=True, detail_supported=True)
    assert lines == ['Rules: --format json (walk_rule.text, _meta.known_limits); --detail for full text', 'one rule',
                     'commit-share, not line-ownership', 'merges excluded by default']


def test_an_empty_list_or_a_missing_field_is_no_location():
    assert rule_text_lines(RESULT, fields=('empty', 'missing.path'), standing_types=frozenset()) == []
