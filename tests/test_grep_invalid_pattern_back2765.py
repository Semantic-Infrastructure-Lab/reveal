"""An invalid ``--grep`` pattern is an invalid request: exit 2, ``RequestValidationError`` (BACK-2765, A3's B9).

``reveal ok.py --grep '('`` printed its failed result and exited 1, the findings code, and ``api.analyze('ok.py',
grep='(')`` returned that failed document instead of raising, because the search's facts said only whether a file was
lost. The pattern is the request's own error (D6): exit 2 on every form, the search's document in JSON naming it as an
invalid request, the API raising it. stderr keeps its line; a file the search could not read keeps exit 3.
"""
import json
import os
import sys

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import RequestValidationError

OK_PY = 'import os\n\n\ndef foo():\n    return 1\n'
TARGETS = ['ok.py', 'd']


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'ok.py').write_text(OK_PY, encoding='utf-8')
    (tmp_path / 'd').mkdir()
    (tmp_path / 'd' / 'a.py').write_text(OK_PY, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize('target', TARGETS)
@pytest.mark.parametrize('fmt', ['text', 'json'])
def test_an_invalid_pattern_exits_2(fx, target, fmt):
    run = _run_reveal_direct(target, '--grep', '(', '--format', fmt)
    assert run.returncode == 2, run.stderr
    assert run.stderr.startswith(f"Error ({target}): invalid pattern '(':")
    if fmt == 'json':
        document = json.loads(run.stdout)
        assert document['type'] == 'grep_results' and document['pattern'] == '('
        assert document['error'].startswith("invalid pattern '(':")
        assert document['meta']['errors'] == [{'code': 'invalid_request', 'message': document['error']}]


@pytest.mark.parametrize('target', TARGETS)
def test_the_api_raises_it(fx, target):
    with pytest.raises(RequestValidationError, match=r"^invalid pattern '\(':"):
        api.analyze(target, grep='(')


@pytest.mark.parametrize('target', TARGETS)
def test_sibling_a_valid_pattern_answers(fx, target):
    run = _run_reveal_direct(target, '--grep', 'foo', '--format', 'json')
    assert run.returncode == 0 and json.loads(run.stdout)['total_hits'] == 1
    assert api.analyze(target, grep='foo')['total_hits'] == 1


@pytest.mark.skipif(sys.platform == 'win32' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                    reason='chmod 000 does not deny reading on Windows or as root')
def test_sibling_a_file_the_search_could_not_read_exits_3(fx):
    denied = fx / 'denied.py'
    denied.write_text(OK_PY, encoding='utf-8')
    denied.chmod(0)
    try:
        assert _run_reveal_direct('denied.py', '--grep', 'foo').returncode == 3
    finally:
        denied.chmod(0o644)
