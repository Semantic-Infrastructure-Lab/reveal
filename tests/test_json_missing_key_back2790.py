"""A missing JSON key is named without Python's quotes (BACK-2790).

``reveal json://d.json/absent`` exits 2 and said ``Error (json://): 'Key not found: absent'``: the json adapter built the
message with ``str()`` of the ``KeyError`` its path walk raised, and ``str(KeyError(text))`` is ``repr(text)``. The same
quoted text reached the JSON answer's ``error``, ``api.query``'s ``RequestValidationError`` and MCP. The sentence is the
walk's own: ``Key not found: absent``, on every transport.

Sibling: an index out of range (an ``IndexError``, whose ``str()`` was never quoted) keeps its message.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api, mcp_server
from reveal.errors import RequestValidationError

pytestmark = pytest.mark.mcp


@pytest.fixture
def data(tmp_path, monkeypatch):
    (tmp_path / 'd.json').write_text('{"list": [1, 2], "nested": {"a": 1}}', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return 'd.json'


# (path in the document, the message)
CASES = [('absent', 'Key not found: absent'), ('nested/zz', 'Key not found: zz'),
         ('list/9', 'Array index out of range: 9')]


@pytest.mark.parametrize('path, says', CASES)
def test_the_cli_names_the_key_without_quotes(data, path, says):
    run = _run_reveal_direct(f'json://{data}/{path}')
    assert run.returncode == 2
    assert f'Error (json://): {says}' in [line.strip() for line in run.stderr.splitlines()]


@pytest.mark.parametrize('path, says', CASES)
def test_the_json_answer_names_the_key_without_quotes(data, path, says):
    run = _run_reveal_direct(f'json://{data}/{path}', '--format', 'json')
    assert run.returncode == 2
    document = json.loads(run.stdout)
    assert document['error'] == says
    assert [error['message'] for error in document['meta']['errors']] == [says]


@pytest.mark.parametrize('path, says', CASES)
def test_the_api_raises_the_same_sentence(data, path, says):
    for call in (lambda: api.query(f'json://{data}/{path}'), lambda: api.query('json', f'{data}/{path}')):
        with pytest.raises(RequestValidationError) as raised:
            call()
        assert str(raised.value) == says


@pytest.mark.parametrize('path, says', CASES)
def test_mcp_says_the_same_sentence(data, path, says):
    assert mcp_server.reveal_run([f'json://{data}/{path}']) == f'[reveal error: {says}]'
