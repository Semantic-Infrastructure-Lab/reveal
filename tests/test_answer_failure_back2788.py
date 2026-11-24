"""``typed.answer_failure`` maps a declared noun's answer to the exception the noun form raises for it (``_failure``):
exit 2 is a ``RequestValidationError`` with the CLI's message (the owner's authored diagnostic first), exit 3 an
``AnalysisFailedError`` carrying the document; an answer that does not fail maps to nothing (BACK-2788)."""
import pytest

from reveal.cli.routing.typed import answer_failure
from reveal.errors import AnalysisFailedError, RequestValidationError
from reveal.utils.results import (AnalysisCompleteness, ExecutionFacts, FailureCause, ResultBuilder,
                                  failure_execution_facts)


class _Plain:
    pass


class _Authored:
    @staticmethod
    def public_diagnostic(result):
        return f"authored: {result['error']}"


def _result(error=None, warnings=()):
    result = dict(ResultBuilder.create('thing', 'x', contract_version='1.0', errors=[], warnings=list(warnings)))
    if error:
        result['error'] = error
    return result


def test_an_invalid_request_is_the_request_error_with_the_answers_message():
    raised = answer_failure(_Plain(), _result('Unknown query: a~~~'), failure_execution_facts(FailureCause.INVALID_REQUEST))
    assert type(raised) is RequestValidationError and str(raised) == 'Unknown query: a~~~'


def test_the_owners_authored_diagnostic_comes_first():
    result = _result('raw')
    raised = answer_failure(_Authored(), result, failure_execution_facts(FailureCause.INVALID_REQUEST))
    assert str(raised) == 'authored: raw' == result['error']


def test_a_failed_analysis_carries_the_document():
    warning = {'type': 'analysis_failed', 'message': 'x.xml: XML parse error'}
    raised = answer_failure(_Plain(), _result(warnings=[warning]), ExecutionFacts(AnalysisCompleteness.FAILED))
    assert isinstance(raised, AnalysisFailedError) and str(raised) == 'x.xml: XML parse error'
    assert raised.result['type'] == 'thing'
    assert raised.result['meta']['warnings'][0] == warning


@pytest.mark.parametrize('facts', [
    ExecutionFacts(AnalysisCompleteness.COMPLETE),
    ExecutionFacts(AnalysisCompleteness.COMPLETE, findings=True),
    ExecutionFacts(AnalysisCompleteness.INCOMPLETE),
    None,
])
def test_an_answer_that_does_not_fail_maps_to_nothing(facts):
    assert answer_failure(_Plain(), _result(), facts) is None


def test_a_result_that_is_no_document_maps_to_nothing():
    assert answer_failure(_Plain(), None, failure_execution_facts(FailureCause.INVALID_REQUEST)) is None
