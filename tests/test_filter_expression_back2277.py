"""filter_expression: one parsed query item back to the filter text it was written as (BACK-2277).

git:// and metrics:// parse a query with parse_query_params and hand the keys no parameter claims
to parse_query_filters; a part with no '=' is a bare key with value True and must not come back
as `key=True` (BACK-2213 `!~`, BACK-2277 `date>D`).
"""
import pytest

from reveal.utils.query_parser import filter_expression, parse_query_filters, parse_query_params


@pytest.mark.parametrize('part', [
    'lines>50', 'date>2026-01-01', 'date<2026-01-01 12:00:00', 'email!~@company.com', '!draft',
    'complexity>=5', 'date<=2026-01-01', 'author~=jo', 'complexity=5..15', 'name=x',
])
def test_round_trips_through_parse_query_params(part):
    ((key, value),) = parse_query_params(part).items()
    rebuilt = filter_expression(key, value)
    assert rebuilt == part
    assert parse_query_filters(rebuilt) == parse_query_filters(part)


def test_bare_key_never_gains_equals_true():
    assert filter_expression('date>2026-01-01', True) == 'date>2026-01-01'
    assert '=True' not in filter_expression('lines>5', True)


def test_a_string_true_value_is_kept():
    # Control: only the parser's bare-key marker (the bool True) drops the value.
    assert filter_expression('flag', 'True') == 'flag=True'
