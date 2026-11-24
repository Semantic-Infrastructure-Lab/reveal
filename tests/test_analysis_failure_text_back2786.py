"""``results.analysis_failure_text``: reveal's own sentence for a failed analysis, the one text the Python API and MCP
give for the same answer (BACK-2786).

It is the authored ``message`` of each ``analysis_failed`` warning, joined with ``'; '``, moved unchanged out of the
API's ``AnalysisFailedError`` mapping (``typed._analysis_failure``), so MCP reads the same rule instead of a copy.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import AnalysisFailedError
from reveal.utils.results import analysis_failure_text


def _failed(message, **extra):
    return {'type': 'analysis_failed', 'count': 1, 'files': ['a.xml'], 'message': message, **extra}


@pytest.mark.parametrize('result, text', [
    ({'meta': {'warnings': [_failed('1 file(s) could not be analyzed completely (XML parse error): a.xml')]}},
     '1 file(s) could not be analyzed completely (XML parse error): a.xml'),
    ({'meta': {'warnings': [_failed('first'), {'type': 'truncated', 'message': 'cut'}, _failed('second')]}},
     'first; second'),
    ({'meta': {'warnings': [{'type': 'analysis_incomplete', 'message': 'Required analysis is incomplete'}]}}, None),
    ({'meta': {'warnings': [_failed('')]}}, None),
    ({'meta': {'warnings': [{'type': 'analysis_failed', 'count': 1}]}}, None),
    ({'meta': {'warnings': []}, 'error': 'analysis failed: XML parse error: no element found'}, None),
    ({'meta': None}, None),
    ({}, None),
    ('not a result', None),
], ids=['one', 'two-joined', 'other-types', 'empty-message', 'no-message', 'error-only', 'meta-none', 'no-meta',
        'not-a-dict'])
def test_the_text_is_the_authored_analysis_failed_messages(result, text):
    assert analysis_failure_text(result) == text


def test_the_api_raises_with_the_text_of_the_clis_document(tmp_path, monkeypatch):
    (tmp_path / 'bad.xml').write_text('<root', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    run = _run_reveal_direct('ast', 'bad.xml', '--format', 'json')
    assert run.returncode == 3, run.stderr
    text = analysis_failure_text(json.loads(run.stdout))
    assert text is not None and 'bad.xml' in text
    with pytest.raises(AnalysisFailedError) as caught:
        api.query('ast', 'bad.xml')
    assert str(caught.value) == text
