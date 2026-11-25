"""An error-stage retirement answers a JSON request with the invalid-request document (BACK-2627 note #9 item 3).

At the cut every note-stage RETIREMENTS row turns to ``error`` (exit 2, the row's text). In text mode that is one stderr
line, ``error: TEXT``. With ``--format json`` stdout used to be empty on every form (a path read, a declared noun's flag,
a URI key, a subcommand, a scheme, the request note), where every other refusal on the same route answers with its
invalid-request document (D16: the envelope on every answer; BACK-2756 cell 21j for path reads). Each route now answers
the row with its own invalid-request document, the row's text as its message, through one shared function
(stormy-rainbow-1124 retire ruling 4); the text line on stderr is unchanged.

Each case is compared with a refusal the same route already answers (an invalid value): the two documents have one
shape, type and source, and differ in the message only. Text mode is the unchanged control; the Python API raises
``RequestValidationError`` with the row's text (BACK-2803).
"""
import json
import re
from dataclasses import replace

import pytest

from conftest import _run_reveal_in, invalid_request_document
from reveal.cli import invocation
from reveal.cli.invocation import RETIREMENTS, RetiredSpellingError

APP = ('import os\n\n\ndef helper(name):\n    return os.path.join("a", name)\n\n\n'
       'def main():\n    if helper("b"):\n        return 1\n    return 0\n')

# name -> (the row at the error stage, the command line that spells it, a refusal of the same route: an invalid value)
CASES = {
    'path read element flag': ('flag:--deps', ['app.py', 'main', '--deps'],
                               ['app.py', 'main', '--view', 'boundary', '--offset', '1']),
    'path read --search': ('flag:--search', ['app.py', '--search', 'hel'], ['app.py', '--head', 'x']),
    'declared flag': ('param:calls.top', ['calls', '.', '--sort=-callers', '--top', '3'],
                      ['calls', '.', '--sort=-callers', '--limit', 'x']),
    # The URI route refuses a conflict before binding, as it refuses a retired key (a malformed ?limit= is refused after
    # binding, typed by the bound prediction: calls_ranking, where the flag form says calls_query).
    'declared URI key': ('param:calls.top', ['calls://.?sort=-callers&top=3'],
                         ['calls://.?sort=-callers&limit=1&limit=2']),
    'subcommand': ('subcommand:hotspots', ['hotspots', '.'], ['hotspots', '.', '--limit', 'x']),
    'declared scheme': ('scheme:hotspots', ['hotspots://.'], ['hotspots://.?limit=x']),
    'scheme on the URI route': ('scheme:stats', ['stats://.'], ['stats://.', '--limit', 'x']),
}


@pytest.fixture
def proj(tmp_path):
    (tmp_path / 'app.py').write_text(APP, encoding='utf-8')
    return tmp_path


def _at_error(monkeypatch, key):
    row = replace(RETIREMENTS[key], stage='error')
    monkeypatch.setitem(RETIREMENTS, key, row)
    return row


def _error_lines(stderr):
    return [line for line in stderr.splitlines() if line.startswith('error:')]


def _assert_document(result, text, sibling=None):
    """*result* is the invalid-request document saying *text*, exit 2, with the text's one stderr line; *sibling*: the
    route's own refusal of an invalid value, whose type and source the document shares."""
    assert result.returncode == 2, (result.returncode, result.stderr)
    doc = invalid_request_document(result)
    assert doc is not None, (result.stdout[:300], result.stderr)
    assert doc['error'] == text
    assert [error['message'] for error in doc['meta']['errors']] == [text]
    assert _error_lines(result.stderr) == [f'error: {text}'], result.stderr
    if sibling is not None:
        other = invalid_request_document(sibling)
        assert other is not None, sibling.stdout[:300]
        assert (doc['type'], doc['source']) == (other['type'], other['source'])
    return doc


@pytest.mark.parametrize('case', CASES)
def test_an_error_stage_row_answers_json_with_the_routes_invalid_request_document(proj, monkeypatch, case):
    key, argv, refusal = CASES[case]
    row = _at_error(monkeypatch, key)
    sibling = _run_reveal_in(proj, *refusal, '--format', 'json')
    _assert_document(_run_reveal_in(proj, *argv, '--format', 'json'), row.text, sibling)


@pytest.mark.parametrize('case', CASES)
def test_text_mode_keeps_its_one_error_line_and_no_answer(proj, monkeypatch, case):
    """Control: the text form of the same refusal is unchanged."""
    key, argv, _ = CASES[case]
    row = _at_error(monkeypatch, key)
    result = _run_reveal_in(proj, *argv)
    assert result.returncode == 2
    assert result.stdout == ''
    assert _error_lines(result.stderr) == [f'error: {row.text}'], result.stderr


@pytest.mark.parametrize('case', CASES)
def test_the_note_stage_still_answers(proj, case):
    """Sibling: the shipped row (note stage) answers exit 0 with its note in the JSON (a URI's covered row is said by
    the request's one note, BACK-2716)."""
    key, argv, _ = CASES[case]
    assert RETIREMENTS[key].stage == 'note'
    result = _run_reveal_in(proj, *argv, '--format', 'json')
    assert result.returncode == 0, result.stderr
    fields = [w.get('field') for w in json.loads(result.stdout).get('meta', {}).get('warnings', [])
              if w.get('code') == 'retired_spelling']
    assert key in fields or fields == [f"request:{argv[0].partition('://')[0]}"], fields


def test_the_request_note_at_the_error_stage_answers_the_document(proj, monkeypatch):
    """A URI request's own note (``REQUEST_STAGE``) refuses as a row does."""
    monkeypatch.setattr(invocation, 'REQUEST_STAGE', 'error')
    sibling = _run_reveal_in(proj, 'ast://.?limit=x', '--format', 'json')
    result = _run_reveal_in(proj, 'ast://.', '--format', 'json')
    text = _error_lines(result.stderr)[0].removeprefix('error: ') if _error_lines(result.stderr) else ''
    assert text.startswith('an ast:// request is deprecated; use reveal ast'), result.stderr
    _assert_document(result, text, sibling)


def test_a_removed_scheme_answers_the_document_typed_by_its_scheme(proj):
    """python:// ships removed (BACK-2225): no adapter is left, so its document is typed by the scheme it spelled."""
    text = RETIREMENTS['scheme:python'].text
    doc = _assert_document(_run_reveal_in(proj, 'python://version', '--format', 'json'), text)
    assert (doc['type'], doc['source']) == ('python', 'version')


def test_a_stdin_line_answers_as_the_direct_request(proj, monkeypatch):
    """Second transport: each ``--stdin`` command line is the direct request (BACK-2707)."""
    row = _at_error(monkeypatch, 'param:calls.top')
    result = _run_reveal_in(proj, '--stdin', stdin='calls . --sort=-callers --top 3 --format json\n')
    _assert_document(result, row.text)


def test_mcp_reveal_run_returns_the_document_as_the_tool_failure(proj, monkeypatch):
    """Third transport: in JSON mode MCP returns exactly the CLI's document (COMMAND_MODEL "Transports")."""
    from reveal.mcp_server import reveal_run
    row = _at_error(monkeypatch, 'flag:--deps')
    monkeypatch.chdir(proj)
    try:
        shown = str(reveal_run(['app.py', 'main', '--deps', '--format', 'json']))
    except Exception as exc:  # a raised tool error is the refusal on MCP; its text is the measured outcome
        shown = str(exc)
    body = shown[shown.index('{'):shown.rindex('}') + 1] if '{' in shown else ''
    assert body, shown
    doc = json.loads(body)
    assert doc['error'] == row.text and doc['type'] == 'element_view', shown


def test_the_python_api_raises_the_request_error_with_the_rows_text(proj, monkeypatch):
    """The API takes the error itself, not the document: ``RequestValidationError`` with the row's text, as for every
    other exit 2, the retirement its cause (BACK-2803, ``api._api_exit``)."""
    from reveal import api
    from reveal.errors import RequestValidationError
    row = _at_error(monkeypatch, 'param:calls.top')
    monkeypatch.chdir(proj)
    with pytest.raises(RequestValidationError) as raised:
        api.query('calls', '.', sort='-callers', top=3)
    assert str(raised.value) == row.text
    assert isinstance(raised.value.__cause__, RetiredSpellingError) and raised.value.__cause__.entry == row
