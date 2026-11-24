"""reveal.api.element(PATH, NAME) answers the JSON document ``reveal PATH NAME --format json`` prints and raises as the
CLI exits (D21, BACK-2325): through the CLI's own element route, so every element syntax the CLI reads answers
(``Class.method``, ``:LINE``, ``:A-B``, ``TYPE:N``, ``@N``), where the API's own lookup answered None for them.

A miss raises ``ElementNotFoundError`` (it returned None); the other refusals raise the request's class with the CLI's
message. Both transports are given the same spelling of the path (answers echo it, BACK-1366).
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import ConfigValidationError, ElementNotFoundError, PathNotFoundError, RequestValidationError

OK_PY = ('import os\n\n\ndef foo():\n    return 1\n\n\ndef bar():\n    return 2\n\n\ndef baz():\n    return 3\n\n\n'
         'class K:\n    def m(self):\n        return os.sep\n')


@pytest.fixture
def fx(tmp_path, monkeypatch):
    files = {'ok.py': OK_PY, 'README.rst': 'Title\n=====\n\ntext\n', 'd/a.py': OK_PY}
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _cli(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run.returncode, (json.loads(run.stdout) if run.stdout.strip() else None), run.stderr


# --- R14: every element syntax answers the CLI's document ----------------------------------------------------------------

@pytest.mark.parametrize('name', ['K.m', ':4', ':4-5', 'function:2', '@2', '5'])
def test_r14_an_element_syntax_answers_the_clis_document(fx, name):
    code, expected, stderr = _cli('ok.py', name)
    assert code == 0 and expected['type'] == 'code_element', stderr
    assert api.element('ok.py', name) == expected


@pytest.mark.parametrize('name', ['foo', 'K', 'm'])
def test_r14_sibling_a_plain_name_answers_the_clis_document(fx, name):
    code, expected, _ = _cli('ok.py', name)
    assert code == 0
    assert api.element('ok.py', name) == expected


# --- R13: a miss raises, as the CLI exits 2 -------------------------------------------------------------------------------

def test_r13_a_miss_raises_element_not_found(fx):
    code, _, stderr = _cli('ok.py', 'nosuch')
    assert code == 2 and "Element 'nosuch' not found in ok.py" in stderr
    with pytest.raises(ElementNotFoundError) as caught:
        api.element('ok.py', 'nosuch')
    assert isinstance(caught.value, RequestValidationError)
    assert str(caught.value) == "Element 'nosuch' not found in ok.py"


def test_r13_a_missing_path_raises_path_not_found(fx):
    with pytest.raises(PathNotFoundError) as caught:
        api.element('missing.py', 'foo')
    assert isinstance(caught.value, FileNotFoundError) and 'missing.py not found' in str(caught.value)


@pytest.mark.parametrize('path, message', [
    ('README.rst', "No analyzer found for file 'README.rst' (extension: .rst)"),
    ('d', "d is a directory; it has no element 'foo'"),
])
def test_r13_the_other_refusals_raise_the_clis_message(fx, path, message):
    code, _, stderr = _cli(path, 'foo')
    assert code == 2 and message in stderr
    with pytest.raises(RequestValidationError) as caught:
        api.element(path, 'foo')
    assert str(caught.value).splitlines()[0] == message


def test_r13_a_selected_configuration_that_does_not_exist_raises(fx, monkeypatch):
    monkeypatch.setenv('REVEAL_CONFIG', str(fx / 'no-such-dir' / 'config.yaml'))
    assert _cli('ok.py', 'foo')[0] == 2
    with pytest.raises(ConfigValidationError):
        api.element('ok.py', 'foo')


# --- S4 completed for the element route: a miss answers the invalid-request document in JSON ------------------------------

def test_a_miss_answers_the_code_element_document_in_json(fx):
    text = _run_reveal_direct('ok.py', 'nosuch')
    code, document, stderr = _cli('ok.py', 'nosuch')
    assert code == 2 and stderr == text.stderr
    assert document is not None, 'stdout is empty: the miss prints no document'
    assert document['type'] == 'code_element' and document['source'] == 'ok.py'
    assert document['error'] == "Element 'nosuch' not found in ok.py"
    assert document['meta']['errors'] == [{'code': 'invalid_request', 'message': document['error']}]


def test_sibling_the_text_miss_is_unchanged(fx):
    run = _run_reveal_direct('ok.py', 'nosuch')
    assert run.returncode == 2 and run.stdout == ''
    assert run.stderr.splitlines() == [
        "Error: Element 'nosuch' not found in ok.py",
        "Hint: Code extraction matches exact names. For content search, use: reveal ok.py --grep 'nosuch'",
        'Available: foo, bar, baz, m, K']
