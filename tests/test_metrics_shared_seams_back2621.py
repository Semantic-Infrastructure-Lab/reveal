"""Shared seams the Metrics vocabulary migration (BACK-2621) adds or lifts, tested on their own.

where_param is AST's repeatable where lifted into one factory so Metrics declares the same spec.
"""
import pytest

from reveal.utils.query_binding import bind_declared_params
from reveal.utils.query_parser import CliBinding, expression_list, where_param


def test_where_param_is_the_repeatable_filter_expression_declaration():
    spec = where_param('Filter rows', ('noun://p?where=lines>5',))
    assert (spec.name, spec.type, spec.default, spec.role) == ('where', 'array', [], 'filter-expression')
    assert spec.cli == CliBinding(('--where',), action='append')
    assert spec.examples == ('noun://p?where=lines>5',) and spec.description == 'Filter rows'


def test_ast_where_is_built_by_the_factory():
    from reveal.adapters.ast.params import WHERE
    assert WHERE == where_param('Filter expressions, ANDed; repeat --where for multiple bounds')


@pytest.mark.parametrize('value,expected', [('lines>5', ['lines>5']), (['a>1', 'b<2'], ['a>1', 'b<2']),
                                            (('a>1',), ['a>1']), ([], [])])
def test_expression_list_accepts_one_or_many(value, expected):
    assert expression_list(value) == expected


@pytest.mark.parametrize('value', ['', '  ', ['a>1', ''], [1], True, None])
def test_expression_list_rejects_empty_or_non_text(value):
    with pytest.raises(ValueError, match='where requires'):
        expression_list(value)


def test_binder_folds_bare_operator_keys_into_where():
    bound = bind_declared_params((where_param('w'),), 'lines>5&where=functions>=1', transport='uri')
    assert sorted(where_param('w').read(bound)) == ['functions>=1', 'lines>5']
