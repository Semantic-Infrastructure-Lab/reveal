"""Mandatory source-authored nav failure contract; shell codes remain independent."""
import pytest

from reveal.errors import NavSourceFailure
from reveal.utils.results import AnalysisCompleteness, ExecutionFacts, FailureCause, failure_execution_facts

pytestmark = pytest.mark.component


@pytest.mark.parametrize('code', [0, 1, 3])
@pytest.mark.parametrize('cause', [FailureCause.INVALID_REQUEST, FailureCause.ANALYSIS])
def test_carrier_preserves_explicit_code_and_mandatory_facts(code, cause):
    facts = failure_execution_facts(cause)
    failure = NavSourceFailure(code, execution_facts=facts, public_diagnostic='Source unavailable\n  Inspect the request.')
    assert isinstance(failure, SystemExit) and not isinstance(failure, Exception)
    assert failure.code == code and failure.args == (code,)
    assert failure.execution_facts is facts
    assert failure.public_diagnostic == 'Source unavailable\n  Inspect the request.'
    with pytest.raises(SystemExit) as caught:
        raise failure
    assert caught.value is failure


def test_fields_are_required_and_plain_system_exit_has_no_authored_origin():
    with pytest.raises(TypeError):
        NavSourceFailure(1)
    ordinary = SystemExit(1)
    assert ordinary.code == 1 and not hasattr(ordinary, 'execution_facts')


@pytest.mark.parametrize('facts', [None, {}, 'failed'])
def test_untyped_facts_cannot_claim_authored_origin(facts):
    with pytest.raises(TypeError, match='ExecutionFacts'):
        NavSourceFailure(1, execution_facts=facts, public_diagnostic='unavailable')


@pytest.mark.parametrize('facts', [
    ExecutionFacts(AnalysisCompleteness.COMPLETE),
    ExecutionFacts(AnalysisCompleteness.INCOMPLETE, failures=frozenset({FailureCause.ANALYSIS})),
    ExecutionFacts(AnalysisCompleteness.NOT_STARTED),
    failure_execution_facts(FailureCause.OUTPUT),
])
def test_healthy_partial_or_non_source_facts_are_not_source_failure(facts):
    with pytest.raises(ValueError, match='failed source/selection'):
        NavSourceFailure(1, execution_facts=facts, public_diagnostic='unavailable')


@pytest.mark.parametrize('diagnostic', ['', '  ', None])
def test_diagnostic_is_required_public_text(diagnostic):
    with pytest.raises((TypeError, ValueError)):
        NavSourceFailure(1, execution_facts=failure_execution_facts(FailureCause.INVALID_REQUEST),
                         public_diagnostic=diagnostic)


def test_exit_code_is_explicit_integer_not_a_derived_fact():
    with pytest.raises(TypeError, match='integer'):
        NavSourceFailure(True, execution_facts=failure_execution_facts(FailureCause.ANALYSIS),
                         public_diagnostic='unavailable')
