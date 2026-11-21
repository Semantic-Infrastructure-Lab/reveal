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
                                  {'implementations_limit': value} if transport == 'typed' else 'implementations_limit='+value,
                                  transport=transport)
    spec = next(s for s in ContractsAdapter.PARAM_SPECS if s.name == 'implementations_limit')
    assert spec.read(params) == expected


@pytest.mark.parametrize('query', ['implementations_limit', 'implementations_limit=true', 'implementations_limit=false', 'implementations_limit=-1', 'implementations_limit=1.5',
                                    'implementations_limit=1e3', 'implementations_limit=1.0e3', 'implementations_limit=garbage', 'implementations_limit='])
def test_impls_rejects_boolean_fraction_and_scientific_forms(query):
    with pytest.raises(ValueError, match='implementations_limit'):
        bind_declared_params(ContractsAdapter.PARAM_SPECS, query, transport='uri')


def test_declaration_defaults_roles_polarity_and_consumption():
    specs = {spec.name: spec for spec in ContractsAdapter.PARAM_SPECS}
    assert set(specs) == {'abstract_only', 'implementations', 'implementations_limit'}
    assert specs['abstract_only'].default is False
    assert specs['implementations'].default is True
    assert specs['implementations'].cli.flags == ('--implementations',)
    assert specs['implementations'].cli.metavar == 'on|off'
    assert [(l.name, l.flag) for l in specs['implementations'].legacy] == [('no_implementations', '--no-implementations')]
    assert [(l.name, l.flag) for l in specs['implementations_limit'].legacy] == [('impls', '--impls')]
    assert specs['implementations'].role == specs['abstract_only'].role == 'analysis'
    assert specs['implementations_limit'].default == 5 and specs['implementations_limit'].role == 'presentation'
    assert specs['implementations_limit'].zero_policy == 'all'
    with collect_query_keys() as keys:
        bound = bind_declared_params(ContractsAdapter.PARAM_SPECS, 'implementations_limit=3.0', transport='uri')
        assert keys.used == set()
        assert set(dict.keys(bound)) == {'implementations_limit'}
        assert specs['implementations_limit'].read(bound) == 3
        assert keys.used == {'implementations_limit', 'impls'}  # a read consumes the legacy word's key too
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
    assert params['implementations']['examples'] == ['implementations=off']
    assert params['implementations_limit']['examples'] == ['implementations_limit=20', 'implementations_limit=0']
    assert params['implementations_limit']['role'] == 'presentation'
    assert schema['execution_policy'] == {'default_fail_on': 'none', 'fail_on': ['none']}
