"""Explicit outcome policy can reuse finalization without generated bindings."""

from argparse import Namespace

import pytest

from reveal.cli.routing.declared import emit_declared_result
from reveal.errors import RequestValidationError
from reveal.utils.results import AnalysisCompleteness, ExecutionFacts, ResultBuilder


def test_validation_exception_keeps_library_valueerror_contract():
    with pytest.raises(ValueError, match='invalid filter'):
        raise RequestValidationError('invalid filter')


def test_existing_finalizer_accepts_explicit_owner_default(capsys):
    result = ResultBuilder.create('ast_query', '.', data={'results': []})
    args = Namespace(format='json', fail_on=None)
    emit_declared_result(result, args, 'ast', lambda *a, **k: None,
                         ExecutionFacts(AnalysisCompleteness.COMPLETE), default_fail_on='none')
    assert 'ast_query' in capsys.readouterr().out


def test_invalid_explicit_default_is_rejected():
    args = Namespace(format='json', fail_on=None)
    with pytest.raises(ValueError, match='unsupported findings gate'):
        emit_declared_result({}, args, 'ast', lambda *a, **k: None,
                             ExecutionFacts(AnalysisCompleteness.COMPLETE), default_fail_on='unknown')
