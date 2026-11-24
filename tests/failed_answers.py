"""A failed URI answer, read where each transport carries it (BACK-2788).

``api.query(URI)`` raises a declared noun's failed answer as its noun form does: a failed analysis (the CLI's exit 3)
is ``AnalysisFailedError`` carrying the document in ``result``, an invalid request (exit 2) a
``RequestValidationError`` carrying the CLI's message only. A test of the evidence such an answer carries reads it
from the exception, or for an invalid request from the CLI's own JSON document, after checking that the API raised
that document's message.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import query
from reveal.errors import AnalysisFailedError, RequestValidationError


def failed_query(uri, *args, **controls):
    """The document of an answer ``api.query`` raises as a failed analysis (the CLI's exit 3)."""
    with pytest.raises(AnalysisFailedError) as raised:
        query(uri, *args, **controls)
    assert raised.value.result is not None, 'a failed answer carries its document'
    return raised.value.result


def refused_query(uri):
    """The CLI's JSON document of a URI request ``api.query`` refuses as invalid (exit 2): the API raises its error."""
    with pytest.raises(RequestValidationError) as raised:
        query(uri)
    run = _run_reveal_direct(uri, '--format', 'json')
    assert run.returncode == 2, run.stderr
    document = json.loads(run.stdout)
    assert document['error'] == str(raised.value)
    return document


def answered(uri, *args, **controls):
    """``(document, failed)``: the answer ``api.query`` returns, or the document of the failed analysis it raises."""
    try:
        return query(uri, *args, **controls), False
    except AnalysisFailedError as raised:
        assert raised.result is not None, 'a failed answer carries its document'
        return raised.result, True
