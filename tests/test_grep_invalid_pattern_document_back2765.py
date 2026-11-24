"""An invalid ``--grep`` pattern answers the path read's invalid-request document in JSON (ruling S4, BACK-2765).

A path read refuses a request it cannot answer with one document, whatever the refusal (a usage error, a missing
path, an invalid ``--range``): the facet of the path as typed (``file_structure`` for a file, ``directory_tree`` for a
directory), the message in ``error`` and ``meta.errors``. An invalid ``--grep`` pattern exited 2 but printed the
search's own ``grep_results`` document carrying the error. It is a refusal of the path read too, so it answers the same
document; stderr, the exit and the API's ``RequestValidationError`` stay as they were.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import RequestValidationError

OK_PY = 'def foo():\n    return 1\n'
FACET = {'ok.py': 'file_structure', 'd': 'directory_tree'}
REFUSAL_KEYS = {'contract_version', 'type', 'source', 'source_type', 'meta', 'error'}


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'ok.py').write_text(OK_PY, encoding='utf-8')
    (tmp_path / 'd').mkdir()
    (tmp_path / 'd' / 'a.py').write_text(OK_PY, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, json.loads(run.stdout)


@pytest.mark.parametrize('target', ['ok.py', 'd'])
def test_an_invalid_pattern_answers_the_path_reads_invalid_request_document(fx, target):
    run, document = _json(target, '--grep', '(')
    assert run.returncode == 2
    assert set(document) == REFUSAL_KEYS
    assert document['type'] == FACET[target] and document['source'] == target
    assert document['error'].startswith("invalid pattern '(':")
    assert document['meta']['errors'] == [{'code': 'invalid_request', 'message': document['error']}]


def test_sibling_an_invalid_range_answers_that_document(fx):
    run, document = _json('ok.py', '--range', 'zz')
    assert run.returncode == 2
    assert set(document) == REFUSAL_KEYS and document['type'] == 'file_structure'


@pytest.mark.parametrize('target', ['ok.py', 'd'])
def test_sibling_stderr_text_and_the_api_are_unchanged(fx, target):
    run = _run_reveal_direct(target, '--grep', '(')
    assert run.returncode == 2 and run.stdout == ''
    assert run.stderr.startswith(f"Error ({target}): invalid pattern '(':")
    with pytest.raises(RequestValidationError, match=r"^invalid pattern '\(':"):
        api.analyze(target, grep='(')


@pytest.mark.parametrize('target', ['ok.py', 'd'])
def test_control_a_valid_pattern_answers_the_search(fx, target):
    run, document = _json(target, '--grep', 'foo')
    assert run.returncode == 0 and document['type'] == 'grep_results' and document['total_hits'] == 1
