"""Opt-in execution policy: owner facts, rather than presentation or child codes."""
from dataclasses import FrozenInstanceError

import pytest

from reveal.utils import results


def facts(completeness='COMPLETE', *, findings=False, failures=()):
    return results.ExecutionFacts(
        getattr(results.AnalysisCompleteness, completeness), findings=findings,
        failures=frozenset(getattr(results.FailureCause, cause) for cause in failures))


@pytest.mark.parametrize('state,failures,findings,gate,expected', [
    ('COMPLETE', (), False, 'none', 0),
    ('COMPLETE', (), True, 'none', 0),
    ('COMPLETE', (), True, 'findings', 1),
    ('NOT_APPLICABLE', (), False, 'findings', 0),
    ('INCOMPLETE', (), False, 'none', 3),
    ('INCOMPLETE', (), True, 'findings', 3),
    ('FAILED', (), True, 'none', 3),
    ('COMPLETE', ('ANALYSIS',), True, 'none', 3),
    ('COMPLETE', ('INVALID_REQUEST',), False, 'none', 2),
    ('INCOMPLETE', ('INVALID_REQUEST',), True, 'findings', 3),
    ('COMPLETE', ('ANALYSIS', 'INVALID_REQUEST'), False, 'none', 3),
    ('COMPLETE', ('OUTPUT', 'INVALID_REQUEST'), False, 'none', 3),
])
def test_declared_facts_control_exit(state, failures, findings, gate, expected):
    assert results.execution_exit_code(
        facts(state, findings=findings, failures=failures), fail_on=gate) == expected


@pytest.mark.parametrize('result', [
    {'contracts': [{'name': 'Service'}]},
    {'applicable': False, 'reason': 'selected language has no HTTP surface'},
    {'meta': {'warnings': [{'type': 'truncated', 'field': 'routes',
                             'shown': 0, 'total': 12}]}},
    {'meta': {'warnings': [{'code': 'optional_exclusion'}]}},
    {'meta': {'errors': [{'code': 'optional_child_unavailable'}]}},
])
def test_completed_owner_evidence_is_not_reclassified_by_lists_or_warnings(result):
    observed = results.result_execution_facts(
        result, completeness=results.AnalysisCompleteness.COMPLETE)
    assert results.execution_exit_code(observed, fail_on='findings') == 0


def test_required_partial_error_needs_owner_completeness_evidence():
    result = {'routes': [], 'meta': {'errors': [{'code': 'source_unparsed'}]}}
    observed = results.result_execution_facts(
        result, completeness=results.AnalysisCompleteness.INCOMPLETE)
    assert results.execution_exit_code(observed, fail_on='none') == 3


@pytest.mark.parametrize('cause,expected', [('INVALID_REQUEST', 2), ('ANALYSIS', 3), ('OUTPUT', 3)])
def test_returned_and_caught_failures_share_explicit_cause(cause, expected):
    classified = getattr(results.FailureCause, cause)
    # The same ValueError can be malformed usage or a parser's operational failure.
    error = ValueError('owner supplied failure')
    returned = results.result_execution_facts(
        {'error': str(error)}, completeness=results.AnalysisCompleteness.COMPLETE,
        failure_cause=classified)
    caught = results.failure_execution_facts(classified)
    assert results.execution_exit_code(returned) == expected
    assert results.execution_exit_code(caught) == expected


@pytest.mark.parametrize('result', [None, [], 'not an answer'])
def test_malformed_required_answer_is_not_success(result):
    observed = results.result_execution_facts(
        result, completeness=results.AnalysisCompleteness.COMPLETE)
    assert results.execution_exit_code(observed) == 3


@pytest.mark.parametrize('state,failures,expected', [
    ('INCOMPLETE', (), 0),
    ('FAILED', ('ANALYSIS',), 0),
    ('COMPLETE', ('INVALID_REQUEST',), 2),
    ('INCOMPLETE', ('INVALID_REQUEST',), 2),
    ('FAILED', ('ANALYSIS', 'OUTPUT'), 3),
])
def test_explicit_legacy_scan_override_is_scoped(state, failures, expected):
    assert results.execution_exit_code(
        facts(state, failures=failures, findings=True), fail_on='findings',
        legacy_scan_override=True) == expected


@pytest.mark.parametrize('state,failures,findings,expected', [
    ('COMPLETE', (), False, 0),
    ('COMPLETE', (), True, 1),
    ('INCOMPLETE', (), True, 3),
    ('COMPLETE', ('OUTPUT',), False, 3),
    ('COMPLETE', ('INVALID_REQUEST',), False, 2),
])
def test_delivery_closure_cannot_erase_independent_facts(state, failures, findings, expected):
    assert results.execution_exit_code(
        results.merge_execution_facts(facts(state, failures=failures, findings=findings), facts()),
        fail_on='findings') == expected


def test_semantic_aggregation_keeps_failures_findings_and_completeness():
    children = [facts(findings=True), facts('INCOMPLETE'),
                facts(failures=('INVALID_REQUEST',)), facts()]
    merged = results.merge_execution_facts(*children)
    reverse = results.merge_execution_facts(*reversed(children))
    assert merged == reverse
    assert merged.completeness == results.AnalysisCompleteness.INCOMPLETE
    assert merged.findings
    assert merged.failures == frozenset({results.FailureCause.INVALID_REQUEST})
    # Numeric maximum of the child exits would be 3 by accident here; the retained
    # facts also let the scoped legacy override expose the independent usage error.
    assert results.execution_exit_code(merged, fail_on='findings') == 3
    assert results.execution_exit_code(merged, legacy_scan_override=True) == 2


def test_aggregation_does_not_turn_all_declines_into_missing_analysis():
    merged = results.merge_execution_facts(facts('NOT_APPLICABLE'), facts('NOT_APPLICABLE'))
    assert merged.completeness == results.AnalysisCompleteness.NOT_APPLICABLE
    assert results.execution_exit_code(merged) == 0
    mixed = results.merge_execution_facts(merged, facts())
    assert mixed.completeness == results.AnalysisCompleteness.COMPLETE


def test_execution_facts_are_typed_and_immutable():
    with pytest.raises((TypeError, ValueError)):
        results.ExecutionFacts('unknown')
    with pytest.raises((TypeError, ValueError)):
        results.ExecutionFacts(results.AnalysisCompleteness.COMPLETE, failures={'analysis'})
    with pytest.raises(FrozenInstanceError):
        facts().findings = True


def test_unknown_gate_and_absent_aggregate_evidence_are_rejected():
    with pytest.raises(ValueError):
        results.execution_exit_code(facts(), fail_on='unknown')
    with pytest.raises(ValueError):
        results.merge_execution_facts()


@pytest.mark.parametrize('result,expected', [
    ({'meta': {'errors': [{'code': 'source_unparsed'}]}}, 'ok'),
    ({'error': 'required failure'}, 'failed'),
    ({'applicable': False}, 'not_applicable'),
    ({'meta': {'warnings': [{'type': 'truncated'}]}}, 'truncated'),
])
def test_legacy_outcome_owner_negative_control(result, expected):
    assert results.outcome_of(result) == expected
