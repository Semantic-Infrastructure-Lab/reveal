"""The binder's empty-value rule refuses an empty walk pattern (BACK-2730), the shared owner's unit test.

BACK-2736's one rule (``query_binding._reject_empty_terms``) refuses an empty or blank term in any spelling of a term
control. ``exclude`` is the walk control, not a term (COMMAND_MODEL "Walk exclusion"), but an empty pattern states no
exclusion and answered as none: the same rule now refuses it, saying it needs a pattern. ``reject_empty_walk_patterns``
applies it to the ``--exclude`` flag every walking parser carries, declared or not.
"""
import pytest

from reveal.errors import RequestValidationError
from reveal.utils.match_terms import PATTERN_EXAMPLES, empty_term_message
from reveal.utils.query_binding import prepare_declared_params, reject_empty_walk_patterns
from reveal.utils.query_parser import exclude_param, where_param

SPECS = (exclude_param(), where_param('filters'))


def _refused(call, message):
    with pytest.raises(RequestValidationError) as refused:
        call()
    assert str(refused.value) == message


@pytest.mark.parametrize('query', ['exclude=', 'exclude=tests&exclude=', 'exclude=&exclude=tests'])
def test_an_empty_uri_pattern_is_refused_in_any_occurrence(query):
    _refused(lambda: prepare_declared_params(SPECS, query, 'uri'), 'exclude needs a pattern: --exclude PATTERN')


def test_a_percent_spelling_is_a_literal_pattern():
    """exclude's own codec decodes only its escapes (``%2C``, ``%26``, ``%3D``, ``%25``; BACK-1380): ``%20`` is the
    literal pattern it always was, as a raw-codec key stays literal under BACK-2736."""
    assert dict(prepare_declared_params(SPECS, 'exclude=%20', 'uri'))['exclude'] == ['%20']


@pytest.mark.parametrize('value', ['', ' ', ['tests', '']])
def test_an_empty_typed_pattern_is_refused_named_as_typed(value):
    _refused(lambda: prepare_declared_params(SPECS, {'exclude': value}, 'typed', spelled={'exclude': '--exclude'}),
             '--exclude needs a pattern: --exclude PATTERN')
    _refused(lambda: prepare_declared_params(SPECS, {'exclude': value}, 'typed'),  # an api.query keyword
             'exclude needs a pattern: --exclude PATTERN')


@pytest.mark.parametrize('patterns', [[''], [' '], ['tests', ''], ['tests', '\t']])
def test_the_walk_controls_flag_meets_the_same_rule(patterns):
    _refused(lambda: reject_empty_walk_patterns(patterns), '--exclude needs a pattern: --exclude PATTERN')


@pytest.mark.parametrize('patterns', [[], ['tests'], ['tests', '*.min.js'], ['a,b']])
def test_real_patterns_pass(patterns):
    reject_empty_walk_patterns(patterns)  # no exception: a pattern, or no flag at all, is a request
    prepared = prepare_declared_params(SPECS, {'exclude': patterns} if patterns else {}, 'typed')
    assert dict(prepared).get('exclude', []) in (patterns, patterns[0] if len(patterns) == 1 else patterns)


def test_a_term_still_needs_a_term():
    """Negative control: match and where keep BACK-2736's wording; only the walk control says pattern."""
    _refused(lambda: prepare_declared_params(SPECS, 'where=', 'uri'), 'where needs a term: --where FIELD OP VALUE')
    assert empty_term_message('--match', '--match TEXT') == '--match needs a term: --match TEXT'
    assert PATTERN_EXAMPLES == {'exclude': '--exclude PATTERN'}
