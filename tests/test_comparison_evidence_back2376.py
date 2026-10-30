"""Comparison evidence has one owner independent of the command's public identity."""

from copy import deepcopy

import pytest

from reveal.adapters.architecture import ArchitectureAdapter
from reveal.diff.architecture_diff import (
    comparison_answer_requirement_error,
    comparison_execution_facts,
)
from reveal.utils.results import AnalysisCompleteness as State
from reveal.utils.results import (
    ExecutionFacts, FailureCause, ResultBuilder, execution_exit_code,
)


IDENTITIES = ['architecture_diff', 'overview_diff']


def _result(identity, data=None, **kwargs):
    return ResultBuilder.create(identity, 'fixture', data=data, **kwargs)


@pytest.mark.parametrize('identity', IDENTITIES)
@pytest.mark.parametrize('analysis', [
    {'complete': True, 'basis': 'identical_tree', 'snapshots': {}},
    {'complete': True, 'basis': 'snapshots', 'snapshots': {
        side: {'imports': 'complete', 'complexity': 'complete'} for side in ('base', 'head')}},
])
def test_complete_comparison_keeps_proof_and_diagnostics(identity, analysis):
    result = _result(identity, {'analysis': analysis}, confidence=0.0,
                     warnings=[{'type': 'truncated', 'message': 'recorded ranking cut'}])
    before = deepcopy(result)
    assert comparison_answer_requirement_error(result) is None
    assert comparison_execution_facts(result) == ExecutionFacts(State.COMPLETE)
    assert result == before


@pytest.mark.parametrize('identity', IDENTITIES)
@pytest.mark.parametrize('analysis', [None, {}, {'complete': None}, {'complete': 'true'}, {'complete': 1}])
def test_absent_or_malformed_comparison_proof_is_not_success(identity, analysis):
    result = _result(identity, None if analysis is None else {'analysis': analysis})
    assert 'completeness evidence' in comparison_answer_requirement_error(result)
    assert comparison_execution_facts(result).completeness is State.INCOMPLETE
    assert execution_exit_code(comparison_execution_facts(result), fail_on='none') == 3


@pytest.mark.parametrize('identity', IDENTITIES)
def test_incomplete_comparison_keeps_canonical_proof_but_fails_execution(identity):
    result = _result(identity, {'analysis': {'complete': False, 'basis': 'snapshots', 'snapshots': {
        'base': {'imports': 'complete', 'complexity': 'complete'},
        'head': {'imports': 'complete', 'complexity': 'incomplete'},
    }}, 'deltas': None})
    assert comparison_answer_requirement_error(result) is None
    assert comparison_execution_facts(result) == ExecutionFacts(State.INCOMPLETE)
    assert execution_exit_code(comparison_execution_facts(result), fail_on='none') == 3


@pytest.mark.parametrize('identity', IDENTITIES)
@pytest.mark.parametrize('top_error', [False, True])
def test_attributed_preanalysis_rejection_stays_usage(identity, top_error):
    result = _result(identity, {'error': 'invalid ref'} if top_error else None,
                     errors=[{'code': 'invalid_request', 'message': 'invalid ref'}])
    expected = ExecutionFacts(State.NOT_STARTED, failures=frozenset({FailureCause.INVALID_REQUEST}))
    assert comparison_execution_facts(result) == expected
    assert comparison_answer_requirement_error(result) is None
    assert comparison_answer_requirement_error(result, expected) is None
    assert execution_exit_code(expected, fail_on='none') == 2


@pytest.mark.parametrize('identity', IDENTITIES)
@pytest.mark.parametrize('warning', ['analysis_failed', 'parse_recovered', 'partial_parse',
                                    'worker_lost', 'analysis_incomplete'])
def test_independent_required_loss_beats_usage_even_without_analysis(identity, warning):
    result = _result(identity, errors=[{'code': 'invalid_request', 'message': 'invalid entry'}],
                     warnings=[{'type': warning, 'message': 'independent required loss'}])
    facts = comparison_execution_facts(result)
    assert facts.completeness is State.INCOMPLETE
    assert facts.failures == frozenset({FailureCause.INVALID_REQUEST})
    assert execution_exit_code(facts, fail_on='none') == 3


@pytest.mark.parametrize('identity', IDENTITIES)
@pytest.mark.parametrize('complete,expected', [(True, 2), (False, 3)])
def test_usage_cause_does_not_replace_explicit_snapshot_state(identity, complete, expected):
    result = _result(identity, {'analysis': {'complete': complete}},
                     errors=[{'code': 'invalid_request', 'message': 'invalid entry'}])
    assert execution_exit_code(comparison_execution_facts(result), fail_on='none') == expected


@pytest.mark.parametrize('identity', IDENTITIES)
@pytest.mark.parametrize('prior', [ExecutionFacts(State.COMPLETE), ExecutionFacts(State.INCOMPLETE),
                                 ExecutionFacts(State.FAILED)])
def test_later_usage_error_cannot_excuse_dropped_prior_proof(identity, prior):
    result = _result(identity, errors=[{'code': 'invalid_request', 'message': 'later usage'}])
    assert 'completeness evidence' in comparison_answer_requirement_error(result, prior)


@pytest.mark.parametrize('identity', IDENTITIES)
@pytest.mark.parametrize('code,expected', [('child_failure', State.INCOMPLETE),
                                        ('E_ARCHITECTURE_ANALYSIS', State.FAILED)])
def test_required_errors_preserve_failure_classification(identity, code, expected):
    result = _result(identity, {'analysis': {'complete': True}},
                     errors=[{'code': code, 'message': 'required child failure'}])
    assert comparison_execution_facts(result).completeness is expected


def test_ordinary_architecture_alias_does_not_require_comparison_proof(tmp_path):
    owner = ArchitectureAdapter(str(tmp_path))
    result = owner.get_structure()
    result['analysis'] = {'complete': False}
    assert owner.answer_requirement_error(result, 'overview') is None
    assert ArchitectureAdapter.execution_facts(result) == ExecutionFacts(State.COMPLETE)
