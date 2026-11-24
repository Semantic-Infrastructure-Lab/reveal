"""An element read inherits the structure's facts (BACK-2775, D21, ruling S3 of BACK-2325).

``reveal bad.xml b`` said "Element 'b' not found", exit 2, while ``reveal bad.xml`` exits 3: nothing asked whether the
file could be read at all before reporting a miss. Now a miss first asks the structure: a file whose parse failed (XML,
notebook JSON) answers that failure, exit 3 naming it (the Python API raises ``AnalysisFailedError``); a file that is not
the document its type needs (a ``.docx`` that is not a zip, a notebook that is a list) is an invalid request, exit 2
naming it (``RequestValidationError``), as the bare read is. The answer carries the cause, so MCP names it too.

Controls that must not move: a line read of a broken file (``reveal bad.xml :1``, no parse needed) answers, a recovered
parse (a Python syntax error) and a valid file still say "not found", exit 2.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import AnalysisFailedError, RequestValidationError

OK_PY = 'import os\n\n\ndef foo():\n    return 1\n'

# file, element, exit, the cause the bare read names (a substring of its error), the document's error code
FAILED = [
    ('bad.xml', 'b', 3, 'XML parse error', 'analysis'),
    ('bad.ipynb', 'x', 3, 'Expecting value', 'analysis'),
    ('bad.docx', 'x', 2, 'Invalid ZIP archive', 'invalid_request'),
    ('shape.ipynb', 'x', 2, 'not a notebook', 'invalid_request'),
]
IDS = [f'{name} {element}' for name, element, *_ in FAILED]


@pytest.fixture
def fx(tmp_path, monkeypatch):
    files = {'ok.py': OK_PY, 'syn.py': 'def ok():\n    pass\n\ndef bad(:\n    pass\n', 'bad.xml': '<a><b></a>\n',
             'bad.ipynb': 'nope', 'shape.ipynb': '[1, 2, 3]\n', 'bad.docx': 'notzip'}
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _bare(name):
    """The bare read's exit, its error (the JSON document's) and its stderr error line."""
    run = _run_reveal_direct(name, '--format', 'json')
    return run.returncode, json.loads(run.stdout)['error'], run.stderr.splitlines()[0]


@pytest.mark.parametrize('name, element, code, cause, error_code', FAILED, ids=IDS)
def test_the_cli_answers_the_structures_failure_not_a_miss(fx, name, element, code, cause, error_code):
    bare_code, error, line = _bare(name)
    assert bare_code == code and cause in error
    run = _run_reveal_direct(name, element)
    assert run.returncode == code
    assert run.stdout == ''
    assert run.stderr == f'{line}\n', 'the file route\'s own error line, not "Element ... not found"'


@pytest.mark.parametrize('name, element, code, cause, error_code', FAILED, ids=IDS)
def test_the_json_document_names_the_cause(fx, name, element, code, cause, error_code):
    _, error, line = _bare(name)
    run = _run_reveal_direct(name, element, '--format', 'json')
    assert run.returncode == code and run.stderr == f'{line}\n'
    document = json.loads(run.stdout)
    assert document['type'] == 'code_element' and document['source'] == name
    assert document['error'] == error
    assert document['meta']['errors'] == [{'code': error_code, 'message': error}]


@pytest.mark.parametrize('name, element, code, cause, error_code', FAILED, ids=IDS)
def test_the_python_api_raises_as_the_cli_exits(fx, name, element, code, cause, error_code):
    _, error, _ = _bare(name)
    expected = json.loads(_run_reveal_direct(name, element, '--format', 'json').stdout or 'null')
    if code == 3:
        with pytest.raises(AnalysisFailedError) as caught:
            api.element(name, element)
        assert caught.value.result == expected
    else:
        with pytest.raises(RequestValidationError) as caught:
            api.element(name, element)
    assert str(caught.value) == error


@pytest.mark.parametrize('name, element, code, cause, error_code', FAILED, ids=IDS)
def test_the_answer_carries_the_cause_to_mcp(fx, name, element, code, cause, error_code):
    from reveal.mcp_server import reveal_run
    text = reveal_run([name, element])
    assert cause in text and 'not found' not in text


# --- controls: the same before and after ---------------------------------------------------------------------------------

def test_control_the_bare_read_of_a_broken_file_exits_3(fx):
    assert _run_reveal_direct('bad.xml').returncode == 3


def test_control_a_line_read_of_a_broken_file_needs_no_parse(fx):
    run = _run_reveal_direct('bad.xml', ':1')
    assert run.returncode == 0 and '<a><b></a>' in run.stdout


@pytest.mark.parametrize('name', ['syn.py', 'ok.py'])
def test_control_a_recovered_parse_or_a_valid_file_still_says_not_found(fx, name):
    run = _run_reveal_direct(name, 'nosuch')
    assert run.returncode == 2
    assert run.stderr.startswith(f"Error: Element 'nosuch' not found in {name}\n")
