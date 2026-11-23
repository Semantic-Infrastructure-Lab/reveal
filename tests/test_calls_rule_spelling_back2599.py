"""BACK-2599 (teaching T6a finding 2): the calls rule sentences name the flags, not query spellings. The callee walk's
rule said '(builtins=true shows them)' and the ranking's '(builtins=true ranks them)' and 'as ?callers=NAME counts
them', while every other teaching surface names --builtins and --callers (BACK-2713)."""

import re

import pytest

from reveal.adapters.calls.adapter import _callees_rule
from reveal.adapters.calls.index import _RANK_RULE

QUERY_SPELLING = re.compile(r'\b\w+=true\b|\?\w+=')


@pytest.mark.parametrize('include_builtins', [False, True])
def test_callee_walk_rule_names_the_flag(include_builtins):
    text = _callees_rule(2, include_builtins, [])['text']
    assert not QUERY_SPELLING.search(text), text
    assert ('(--builtins shows them)' in text) is (not include_builtins)


def test_rank_rule_names_the_flags():
    assert not QUERY_SPELLING.search(_RANK_RULE), _RANK_RULE
    assert 'as --callers NAME counts them' in _RANK_RULE and '(--builtins ranks them)' in _RANK_RULE


def test_the_pattern_bites():
    """Positive control: the old spellings match."""
    assert QUERY_SPELLING.search('builtins hidden (builtins=true shows them)')
    assert QUERY_SPELLING.search('matched by name as ?callers=NAME counts them')
