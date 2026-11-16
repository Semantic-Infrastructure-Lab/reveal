"""Shared seams the Metrics vocabulary migration (BACK-2621) adds or lifts, tested on their own.

where_param is AST's repeatable where lifted into one factory so Metrics declares the same spec.
"""
import pytest

from reveal.utils.query_binding import bind_declared_params
from reveal.utils.query_parser import CliBinding, expression_list, where_param


def test_where_param_is_the_repeatable_filter_expression_declaration():
    spec = where_param('Filter rows', ('noun://p?where=lines>5',))
    assert (spec.name, spec.type, spec.default, spec.role) == ('where', 'array', [], 'filter-expression')
    assert spec.cli == CliBinding(('--where',)) and spec.repeatable and spec.cli_action == 'append'  # BACK-2654
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
    """A bound adapter with a canonical control and a legacy parameter of its own (not an alias)."""
    from reveal.utils.query_parser import ParamSpec as _Spec
    PARAM_SPECS = (_Spec('limit', 'integer', 'rows', None, int),
                   _Spec('old', 'integer', 'legacy rows', None, int),
                   _Spec('kept', 'integer', 'a name with no row', None, int))

    def get_structure(self):
        return {'type': 'stub', 'meta': {'warnings': []}}


@pytest.fixture
def legacy_row(monkeypatch):
    from reveal.cli import invocation
    monkeypatch.setitem(invocation.RETIREMENTS, 'param:stub.old',
                        invocation.Retirement('stub ?old=N', '?limit=N'))


def _notes(result):
    return [w['message'] for w in result['meta']['warnings'] if w.get('code') == 'retired_spelling']


def _api_answer(uri, overrides):
    from reveal.api import _noted_answer
    return _noted_answer('stub', uri, overrides, _LegacyNoun().get_structure)


@pytest.mark.parametrize('uri,overrides', [('stub://p?old=3', {}), ('stub://p', {'old': 3})])
def test_api_notes_a_legacy_parameter_as_the_cli_does(legacy_row, uri, overrides):
    """A retired spelling gets its D5 note on api.query as on the URI and subcommand routes, from the URI key
    or the typed keyword (BACK-2621; BACK-2654: from its RETIREMENTS row alone, declared or not)."""
    result = _api_answer(uri, overrides)
    assert any('stub ?old=N' in note and '?limit=N' in note for note in _notes(result)), result['meta']


def test_api_notes_a_retired_key_whatever_the_adapter_declares(legacy_row, monkeypatch):
    """BACK-2654 rule 11: RETIREMENTS is the one source of notes, as on the CLI (api.query used to note only
    declared aliases and ParamSpec.retired names)."""
    from reveal.cli import invocation
    monkeypatch.setitem(invocation.RETIREMENTS, 'param:stub.other', invocation.Retirement('stub ?other', '?limit'))
    assert _notes(_api_answer('stub://p?other=1&limit=2', {})) == ['stub ?other is deprecated; use ?limit.']


def test_api_keeps_no_note_for_a_spelling_without_a_row(legacy_row):
    """Negative control: a parameter with no RETIREMENTS row notes nothing on any transport."""
    assert _notes(_api_answer('stub://p?kept=1&limit=2', {'kept': 2})) == []


def test_a_global_switch_whose_uri_value_differs_is_rejected(monkeypatch):
    """A global switch whose URI value differs is an invalid request on every noun (BACK-2654 rule 1; it was
    BACK-2621's reject_conflict opt-in). Equal values are accepted once."""
    from argparse import Namespace
    from reveal.cli.routing import flag_specs
    from reveal.errors import RequestValidationError
    spec = flag_specs.FlagSpec('hotspots', '--hotspots', flag_specs._switch('hotspots'))
    monkeypatch.setattr(flag_specs, 'FLAG_SPECS', (spec,))
    args = Namespace(hotspots=True)
    assert flag_specs.inject_query_flags('?hotspots=true', 'metrics', args) == '?hotspots=true'
    with pytest.raises(RequestValidationError, match='--hotspots conflicts with hotspots=false'):
        flag_specs.inject_query_flags('?hotspots=false', 'metrics', args)
    assert flag_specs.inject_query_flags('?view=provenance', 'metrics', args) == '?view=provenance&hotspots=true'
