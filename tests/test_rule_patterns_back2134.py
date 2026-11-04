"""``RuleRegistry._matches_patterns`` answers every pattern shape as before, without a
``RulePrefix(pattern)`` raise-and-swallow per rule/pattern pair (BACK-2134)."""
import itertools

import pytest

import reveal.rules as rules_module
from reveal.rules import RuleRegistry
from reveal.rules.base import BaseRule, RulePrefix

pytestmark = pytest.mark.component


def _legacy(rule_class, patterns):
    """The pre-BACK-2134 body, kept verbatim as the oracle for equivalence."""
    code = rule_class.code
    for pattern in patterns:
        if code == pattern:
            return True
        if code.startswith(pattern):
            return True
        try:
            prefix = RulePrefix(pattern)
            if rule_class.category == prefix:
                return True
        except (ValueError, AttributeError):
            pass
    return False


def _fake(code, category):
    attrs = {'code': code, 'message': 'x'}
    if category != 'absent':
        attrs['category'] = category
    return type(f'Fake{code}', (), attrs)


# exact code, prefix, glob-like, invalid, empty, a RulePrefix value no code starts with
PATTERNS = ['B001', 'B', 'B0', 'b', 'B*', 'B0??', '*', 'B-', 'ZZZ', 'Z9999', '', ' ', 'PERF', 'U', 'unknown', 'E501 ']
PATTERN_LISTS = [[p] for p in PATTERNS] + [[], ['ZZZ', 'B'], ['ZZZ', 'PERF'], ['', 'ZZZ'], ['B*', 'S'], ['Z9999', 'ZZZ', 'M']]
# category differs from the code's own letters: only the RulePrefix branch can match
FAKES = [_fake('ZZ1', RulePrefix.B), _fake('ZZ2', RulePrefix.PERF), _fake('ZZ3', 'B'),
         _fake('ZZ4', None), _fake('ZZ5', 'absent')]


def _all_rules():
    RuleRegistry.discover()
    return list(RuleRegistry._rules) + FAKES


def test_every_pattern_shape_matches_as_before_on_every_registered_rule_and_fake():
    for rule, patterns in itertools.product(_all_rules(), PATTERN_LISTS):
        assert RuleRegistry._matches_patterns(rule, patterns) == _legacy(rule, patterns), (rule.code, patterns)


def test_pinned_answers_for_each_shape():
    by_category = _fake('ZZ1', RulePrefix.B)
    plain = _fake('ZZ3', 'B')
    missing = _fake('ZZ5', 'absent')
    match = RuleRegistry._matches_patterns
    assert match(by_category, ['B'])           # a RulePrefix value matches on category alone
    assert not match(by_category, ['PERF'])
    assert not match(plain, ['B'])             # a plain-string category never equals the enum
    assert not match(missing, ['B'])           # no category attribute: no match, no error
    assert match(missing, [''])                # empty pattern is a prefix of every code
    assert match(missing, ['ZZ5']) and match(missing, ['ZZ'])
    assert not match(missing, ['B*']) and not match(missing, ['zz5'])
    assert not match(missing, [])


def test_non_prefix_patterns_do_not_construct_a_rule_prefix_per_rule_pattern_pair(monkeypatch):
    constructed = []

    def counting(value):
        constructed.append(value)
        return RulePrefix(value)

    monkeypatch.setattr(rules_module, 'RulePrefix', counting)
    rules = _all_rules()
    patterns = ['ZZZ', 'B*', 'unknown', 'PERF', '']
    for rule in rules:
        RuleRegistry._matches_patterns(rule, patterns)
    # once per pattern is acceptable (validated up front); once per pair is the BACK-2134 cost
    assert len(rules) > 10
    assert len(constructed) <= len(patterns), f'{len(constructed)} constructions for {len(rules)} rules x {len(patterns)} patterns'


def test_get_rules_ignore_answer_is_unchanged():
    RuleRegistry.discover()
    for ignore in (['B'], ['ZZZ'], ['B', 'S'], ['B*'], [''], ['PERF']):
        expected = [r for r in RuleRegistry._rules if r.enabled and not _legacy(r, ignore)]
        assert RuleRegistry.get_rules(ignore=ignore) == expected, ignore
