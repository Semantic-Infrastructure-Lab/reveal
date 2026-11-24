"""``api.query(URI)`` raises a missing path as the CLI refuses it (D21, BACK-2788).

The CLI's declared route judges a filesystem resource before the adapter is built: one that does not exist is an
invalid request, exit 2, ``Path not found: PATH``. The Python API's URI form skipped that judgement, so its answer
depended on each noun: ``ast://nope``, ``calls://nope?callers=f`` and ``imports://nope`` returned a document (imports'
naming the absolute path), ``markdown://nope`` raised a bare ``FileNotFoundError`` carrying ``[Errno 2]``, and
``json://nope.json`` / ``xlsx://nope.xlsx`` raised their own wording. The URI form now raises ``PathNotFoundError``
(a ``RequestValidationError`` and still a ``FileNotFoundError``) with the CLI's message.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import PathNotFoundError, RequestValidationError

MISSING = [
    ('ast://nope', 'nope'),
    ('calls://nope?callers=f', 'nope'),
    ('imports://nope', 'nope'),
    ('markdown://nope', 'nope'),
    ('metrics://nope', 'nope'),
    ('json://nope.json', 'nope.json'),
    ('xlsx://nope.xlsx', 'nope.xlsx'),
]
PRESENT = ['ast://d', 'calls://d?callers=f', 'imports://d', 'markdown://d', 'metrics://d', 'json://d.json']


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'd').mkdir()
    (tmp_path / 'd' / 'ok.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'd.json').write_text('{"a": 1}\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize('uri, path', MISSING)
def test_the_uri_form_raises_a_missing_path_as_path_not_found(fx, uri, path):
    with pytest.raises(PathNotFoundError) as raised:
        api.query(uri)
    assert str(raised.value) == f'Path not found: {path}'
    assert isinstance(raised.value, RequestValidationError) and isinstance(raised.value, FileNotFoundError)


def test_a_typed_keyword_does_not_hide_the_missing_path(fx):
    with pytest.raises(PathNotFoundError, match='^Path not found: nope$'):
        api.query('ast://nope', kind='function')


@pytest.mark.parametrize('uri, path', MISSING)
def test_sibling_the_cli_exits_2_with_that_message(fx, uri, path):
    run = _run_reveal_direct(uri, '--format', 'json')
    assert run.returncode == 2
    assert json.loads(run.stdout)['error'] == f'Path not found: {path}'


@pytest.mark.parametrize('uri', PRESENT)
def test_control_an_existing_path_answers(fx, uri):
    assert isinstance(api.query(uri), dict)


def test_control_an_unknown_query_key_stays_the_request_error(fx):
    with pytest.raises(RequestValidationError, match="unsupported control 'bogus'") as raised:
        api.query('calls://d?bogus=1')
    assert not isinstance(raised.value, FileNotFoundError)
