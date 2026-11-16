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


class _LegacyNoun:
    """A bound adapter with a canonical control and a legacy one (its own declared name, not an alias)."""
    from reveal.utils.query_parser import ParamSpec as _Spec
    PARAM_SPECS = (_Spec('limit', 'integer', 'rows', None, int), _Spec('old', 'integer', 'legacy rows', None, int))

    def get_structure(self):
        return {'type': 'stub', 'meta': {'warnings': []}}


@pytest.fixture
def legacy_row(monkeypatch):
    from reveal.cli import invocation
    monkeypatch.setitem(invocation.RETIREMENTS, 'param:stub.old',
                        invocation.Retirement('stub ?old=N', '?limit=N'))


def _notes(result):
    return [w['message'] for w in result['meta']['warnings'] if w.get('code') == 'retired_spelling']


@pytest.mark.parametrize('uri,overrides', [('stub://p?old=3', {}), ('stub://p', {'old': 3})])
def test_api_notes_a_declared_legacy_parameter_as_the_cli_does(legacy_row, uri, overrides):
    """A retired spelling that is a declared parameter of its own (not an alias) gets its D5 note on
    api.query as on the URI and subcommand routes, from the URI key or the typed keyword."""
    from reveal.api import _bound_query_result
    result = _bound_query_result(_LegacyNoun(), 'stub', uri, overrides)
    assert any('stub ?old=N' in note and '?limit=N' in note for note in _notes(result)), result['meta']


def test_api_does_not_note_a_retired_key_the_adapter_does_not_declare(legacy_row, monkeypatch):
    from reveal.api import _bound_query_result
    from reveal.cli import invocation
    monkeypatch.setitem(invocation.RETIREMENTS, 'param:stub.other', invocation.Retirement('stub ?other', '?limit'))
    assert _notes(_bound_query_result(_LegacyNoun(), 'stub', 'stub://p?other=1&limit=2', {})) == []
