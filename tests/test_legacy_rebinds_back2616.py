"""A legacy word that changes what another control means in its request (BACK-2616, ruling Q1 option A).

Git's legacy ``?type=ownership&limit=N`` bounds the commit input, which today is ``--scan-limit N``; ``--view ownership
--limit N`` caps the author rows. ``LegacySpelling.rebinds`` declares that: in a request that spells the legacy word and
selects an answer ``rebinds_when`` accepts, the first control's value is the second's. The binder applies it once all of
the request's sources are joined (the URI, the flags after it, typed keywords, typed overrides), so every transport
binds one request and the request note renders the control the value now sets. The control the value moves to, given
too, is one setting under "Conflicting values": equal values are one, different values are an invalid request naming
both; a typed override replaces the value it overrides, as overrides do.
"""
import pytest

from reveal.utils.query_binding import (apply_declared_overrides, bind_declared_params, bind_prepared_params,
                                        join_uri_and_flags, prepare_declared_params)
from reveal.utils.query_parser import (CliBinding, LegacySpelling, ParamSpec, nonempty_scalar,
                                       nonnegative_display_limit)


def _aggregate(values):
    return values.get('view') == 'agg'


LIMIT = ParamSpec('limit', 'integer', 'Rows', None, lambda v: nonnegative_display_limit(v, name='limit'), minimum=0,
                  cli=CliBinding(('--limit',)))
BUDGET = ParamSpec('budget', 'integer', 'Input', None, lambda v: nonnegative_display_limit(v, name='budget'),
                   minimum=0, cli=CliBinding(('--budget',)))


@pytest.fixture
def specs():
    view = ParamSpec('view', 'string', 'Answer', None, nonempty_scalar, role='operation', cli=CliBinding(('--view',)),
                     legacy=(LegacySpelling('type', rebinds=(('limit', 'budget'),), rebinds_when=_aggregate),))
    return (view, LIMIT, BUDGET)


def _bound(params):
    return {key: dict.get(params, key) for key in ('view', 'limit', 'budget') if dict.get(params, key) is not None}


@pytest.mark.parametrize('query,expected', [
    ('type=agg&limit=3', {'view': 'agg', 'budget': 3}),
    ('limit=3&type=agg', {'view': 'agg', 'budget': 3}),
    ('type=agg&limit=3&budget=3', {'view': 'agg', 'budget': 3}),  # one setting given twice, equal
    ('view=agg&limit=3', {'view': 'agg', 'limit': 3}),  # the canonical word: a row cap
    ('type=rows&limit=3', {'view': 'rows', 'limit': 3}),  # an answer rebinds_when refuses
    ('type=agg', {'view': 'agg'}),
])
def test_a_uri_request_spelling_the_legacy_word_rebinds_once(specs, query, expected):
    params = bind_declared_params(specs, query, transport='uri')
    assert _bound(params) == expected
    assert ('budget' in params._given) == ('budget' in expected) and ('limit' in params._given) == ('limit' in expected)


def test_a_different_value_for_the_control_it_moves_to_names_both(specs):
    with pytest.raises(ValueError, match='budget: conflicting spellings: limit, budget'):
        bind_declared_params(specs, 'type=agg&limit=3&budget=4', transport='uri')


def test_typed_keywords_rebind_as_the_uri_does(specs):
    assert _bound(bind_declared_params(specs, {'type': 'agg', 'limit': 3}, transport='typed')) == \
        {'view': 'agg', 'budget': 3}
    assert _bound(bind_declared_params(specs, {'view': 'agg', 'limit': 3}, transport='typed')) == \
        {'view': 'agg', 'limit': 3}


def test_a_flag_after_a_legacy_uri_is_the_same_request(specs):
    joined = join_uri_and_flags(specs, prepare_declared_params(specs, 'type=agg', 'uri'),
                                prepare_declared_params(specs, {'limit': 3}, 'typed'))
    assert _bound(bind_prepared_params(specs, joined, transport='uri')) == {'view': 'agg', 'budget': 3}


@pytest.mark.parametrize('query,overrides,expected', [
    ('type=agg', {'limit': 3}, {'view': 'agg', 'budget': 3}),
    ('type=agg&limit=3', {'limit': 5}, {'view': 'agg', 'budget': 5}),  # an override replaces what it overrides
    ('type=rows&limit=3', {'view': 'agg'}, {'view': 'agg', 'budget': 3}),  # the override selects the answer
    ('limit=3', {'type': 'agg'}, {'view': 'agg', 'budget': 3}),  # the legacy word typed as a keyword
    ('view=agg', {'limit': 3}, {'view': 'agg', 'limit': 3}),
])
def test_typed_overrides_rebind_after_they_apply(specs, query, overrides, expected):
    params = bind_prepared_params(specs, prepare_declared_params(specs, query, 'uri'), transport='uri')
    assert _bound(apply_declared_overrides(specs, params, overrides)) == expected


def test_a_spec_with_no_rebinds_is_unchanged():
    plain = ParamSpec('view', 'string', 'Answer', None, nonempty_scalar, legacy=(LegacySpelling('type'),))
    params = bind_declared_params((plain, LIMIT, BUDGET), 'type=agg&limit=3', transport='uri')
    assert _bound(params) == {'view': 'agg', 'limit': 3}
