"""Contracts declarations preserve analysis controls and text-only implementer caps."""
import pytest

from reveal.adapters.contracts import ContractsAdapter
from reveal.utils.query_binding import bind_declared_params
from reveal.utils.query_parser import collect_query_keys
from reveal.utils.results import AnalysisCompleteness, ResultBuilder, execution_exit_code


@pytest.mark.parametrize('transport', ['typed', 'uri'])
@pytest.mark.parametrize('value,expected', [('0', 0), ('1', 1), ('3.0', 3), ('20', 20)])
def test_impls_conversion_preserves_legacy_whole_decimals(transport, value, expected):
    params = bind_declared_params(ContractsAdapter.PARAM_SPECS,
                                  {'impls': value} if transport == 'typed' else 'impls='+value,
                                  transport=transport)
    spec = next(s for s in ContractsAdapter.PARAM_SPECS if s.name == 'impls')
    assert spec.read(params) == expected


@pytest.mark.parametrize('query', ['impls', 'impls=true', 'impls=false', 'impls=-1', 'impls=1.5',
                                    'impls=1e3', 'impls=1.0e3', 'impls=garbage', 'impls='])
def test_impls_rejects_boolean_fraction_and_scientific_forms(query):
    with pytest.raises(ValueError, match='impls'):
        bind_declared_params(ContractsAdapter.PARAM_SPECS, query, transport='uri')


def test_declaration_defaults_roles_polarity_and_consumption():
    specs = {spec.name: spec for spec in ContractsAdapter.PARAM_SPECS}
    assert set(specs) == {'abstract_only', 'implementations', 'impls'}
    assert specs['abstract_only'].default is False
    assert specs['implementations'].default is True
    assert specs['implementations'].cli.flags == ('--no-implementations',)
    assert specs['implementations'].cli.action == 'store_false'
    assert specs['implementations'].role == specs['abstract_only'].role == 'analysis'
    assert specs['impls'].default == 5 and specs['impls'].role == 'presentation'
    assert specs['impls'].zero_policy == 'all'
    with collect_query_keys() as keys:
        bound = bind_declared_params(ContractsAdapter.PARAM_SPECS, 'impls=3.0', transport='uri')
        assert keys.used == set()
        assert set(dict.keys(bound)) == {'impls'}
        assert specs['impls'].read(bound) == 3
        assert keys.used == {'impls'}
    resource = ContractsAdapter.RESOURCE_SPEC
    assert resource.cli_default == resource.uri_default == '.'
    assert resource.uri_codec == 'existing-path-first'
    assert ContractsAdapter.RESULT_TYPE == 'contracts'
    assert ContractsAdapter.FINDINGS_POLICIES == ('none',)
    assert ContractsAdapter.DEFAULT_FAIL_ON == 'none'


@pytest.mark.parametrize('evidence', ['recovered', 'unparsed', 'producer_error', 'none', 'harmless', 'unsupported'])
def test_only_owned_missing_evidence_is_incomplete(evidence):
    data, warnings, errors = {}, [], []
    if evidence == 'recovered':
        data['recovered_files'] = ['a.py']
    elif evidence == 'unparsed':
        data['unparsed_files'] = ['a.go']
    elif evidence == 'producer_error':
        errors = [{'code': 'E_CONTRACTS_ANALYSIS', 'file': 'a.ts', 'message': 'OSError: lost input'}]
    elif evidence == 'harmless':
        warnings = [{'type': 'informational', 'message': 'scope information'}]
    elif evidence == 'unsupported':
        data['unsupported_language'] = 'lua'
        warnings = [{'type': 'coverage_gap', 'code': 'W-CONTRACTS-1', 'message': 'documented language coverage'}]
    result = ResultBuilder.create('contracts', '.', confidence=0.0, data=data,
                                  warnings=warnings, errors=errors)
    facts = ContractsAdapter.execution_facts(result)
    incomplete = evidence in ('recovered', 'unparsed', 'producer_error')
    assert facts.completeness is (AnalysisCompleteness.INCOMPLETE if incomplete else AnalysisCompleteness.COMPLETE)
    assert execution_exit_code(facts, fail_on='none') == (3 if incomplete else 0)


def test_schema_preserves_examples_and_declares_roles():
    schema = ContractsAdapter.get_schema()
    params = schema['query_params']
    assert params['abstract_only']['examples'] == ['abstract_only=true']
    assert params['implementations']['examples'] == ['implementations=false']
    assert params['impls']['examples'] == ['impls=20', 'impls=0']
    assert params['impls']['role'] == 'presentation'
    assert schema['execution_policy'] == {'default_fail_on': 'none', 'fail_on': ['none']}
