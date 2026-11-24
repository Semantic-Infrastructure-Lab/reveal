"""Unit tests of the one rendering of an error-stage retirement (``declared.answer_retired_spelling``, BACK-2627) and of
the word-only read of a request refused before it is parsed (``JsonUsageParser.typed_request``).

A route hands the function the error and its own invalid-request Answer builder; in a JSON request the function prints
the process's ``error:`` line and the route's document (without the route's own stderr label) and exits 2, and in every
other case the error goes on unchanged, so text mode and the Python API keep what they did.
"""
import json
from argparse import Namespace

import pytest

from reveal.cli.invocation import RetiredSpellingError, Retirement
from reveal.cli.routing.declared import _invalid_answer, answer_retired_spelling, create_declared_parser

ROW = Retirement('old://', 'new://', 'error')


def _error():
    return RetiredSpellingError('scheme:old', ROW)


def _refusal(calls, args):
    def refusal(text):
        calls.append(text)
        return _invalid_answer(None, 'old', 'src', text, args, result_type='old_answer', default_fail_on='none',
                               label='src')
    return refusal


def test_a_json_request_prints_the_error_line_and_the_routes_document(capsys):
    args, calls = Namespace(format='json'), []
    with pytest.raises(SystemExit) as stopped:
        answer_retired_spelling(_error(), args, _refusal(calls, args))
    assert stopped.value.code == 2
    assert calls == [ROW.text]
    out, err = capsys.readouterr()
    assert err == f'error: {ROW.text}\n'  # the route's own "Error (src):" label is not printed beside it
    document = json.loads(out)
    assert (document['type'], document['source'], document['error']) == ('old_answer', 'src', ROW.text)
    assert document['meta']['errors'] == [{'code': 'invalid_request', 'message': ROW.text}]


@pytest.mark.parametrize('fmt', ['text', None])
def test_text_mode_raises_the_error_unchanged(capsys, fmt):
    args, calls, error = Namespace(format=fmt), [], _error()
    with pytest.raises(RetiredSpellingError) as raised:
        answer_retired_spelling(error, args, _refusal(calls, args))
    assert raised.value is error and calls == []
    assert capsys.readouterr() == ('', '')


def test_a_caller_that_takes_the_answer_keeps_the_error(capsys):
    args, calls, error = Namespace(format='json'), [], _error()
    with pytest.raises(RetiredSpellingError) as raised:
        answer_retired_spelling(error, args, _refusal(calls, args), answer_consumer=lambda answer: None)
    assert raised.value is error and calls == []
    assert capsys.readouterr() == ('', '')


def test_a_route_with_no_document_keeps_the_error(capsys):
    error = _error()
    with pytest.raises(RetiredSpellingError) as raised:
        answer_retired_spelling(error, Namespace(format='json'), lambda text: None)
    assert raised.value is error
    assert capsys.readouterr() == ('', '')


@pytest.mark.parametrize('argv, fmt', [
    (['src', '--format', 'json'], 'json'),
    (['src', '--format=json'], 'json'),
    (['src', '--output', 'json'], 'json'),
    (['src'], 'text'),
    (['src', '--help', '--format', 'json'], 'json'),  # no option's action runs: --help prints nothing
])
def test_typed_request_reads_the_words_without_running_an_option(capsys, argv, fmt):
    args = create_declared_parser('ast').typed_request(argv)
    assert (args.format, args.path) == (fmt, 'src')
    assert capsys.readouterr() == ('', '')


def test_typed_request_lets_a_known_option_take_its_value():
    """``trace --from NAME PATH``: the noun's own parser knows ``--from`` takes a value, so PATH is the target."""
    args = create_declared_parser('trace').typed_request(['--from', 'main', 'src', '--format', 'json'])
    assert (args.format, args.path) == ('json', 'src')


# --- the declared binder (run_declared_command, run_declared_uri) -----------------------------------------------------

def _declared_request(monkeypatch, tmp_path, argv):
    """*argv* (``calls ...``) parsed by the noun's own parser inside its invocation, with ``param:calls.top`` at error."""
    from dataclasses import replace
    from reveal.cli.invocation import RETIREMENTS, Invocation, invocation_scope
    row = replace(RETIREMENTS['param:calls.top'], stage='error')
    monkeypatch.setitem(RETIREMENTS, 'param:calls.top', row)
    (tmp_path / 'app.py').write_text('def main():\n    return 0\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    invocation = Invocation.parse(['reveal', *argv])
    parser = create_declared_parser('calls')
    return row, invocation_scope(invocation), parser, invocation.command_argv


@pytest.mark.parametrize('fmt', ['json', 'text'])
def test_run_declared_command_answers_a_retired_flag_where_the_binder_refuses(monkeypatch, tmp_path, capsys, fmt):
    from reveal.cli.routing.declared import run_declared_command
    row, scope, parser, argv = _declared_request(monkeypatch, tmp_path,
                                                 ['calls', '.', '--sort=-callers', '--top', '3', '--format', fmt])
    with scope:
        args = parser.parse_args(argv)
        if fmt == 'text':
            with pytest.raises(RetiredSpellingError, match='calls'):
                run_declared_command('calls', args)
            return
        with pytest.raises(SystemExit) as stopped:
            run_declared_command('calls', args)
    assert stopped.value.code == 2
    out, err = capsys.readouterr()
    assert err.splitlines()[-1] == f'error: {row.text}'
    document = json.loads(out)
    assert (document['type'], document['source'], document['error']) == ('calls_query', '.', row.text)


def test_run_declared_command_hands_a_consumer_the_error(monkeypatch, tmp_path, capsys):
    """The Python API's noun form passes a consumer: it keeps the error it raised (BACK-2803 maps its class)."""
    from reveal.cli.routing.declared import run_declared_command
    row, scope, parser, argv = _declared_request(monkeypatch, tmp_path,
                                                 ['calls', '.', '--sort=-callers', '--top', '3', '--format', 'json'])
    answers = []
    with scope:
        with pytest.raises(RetiredSpellingError) as raised:
            run_declared_command('calls', parser.parse_args(argv), answer_consumer=answers.append)
    assert raised.value.entry == row and answers == []
    assert capsys.readouterr().out == ''


def test_run_declared_uri_answers_the_request_note_at_the_error_stage(monkeypatch, tmp_path, capsys):
    """The URI route's declared path (a ``--stdin`` URI line, a file the path read routes to a URI): the URI's keys are
    noted before it (``uri._note_retired_spellings``); the request's own note is said as it binds."""
    from reveal.cli import invocation
    from reveal.cli.routing.declared import run_declared_uri
    from reveal.main import create_argument_parser
    _row, scope, _parser, _argv = _declared_request(monkeypatch, tmp_path, ['calls://.?sort=-callers'])
    monkeypatch.setattr(invocation, 'REQUEST_STAGE', 'error')
    with scope:
        args = create_argument_parser('0').parse_args(['calls://.?sort=-callers', '--format', 'json'])
        with pytest.raises(SystemExit) as stopped:
            run_declared_uri('calls://.?sort=-callers', None, args)
    assert stopped.value.code == 2
    out, err = capsys.readouterr()
    document = json.loads(out)
    assert (document['type'], document['source']) == ('calls_query', '.')
    assert document['error'].startswith('a calls:// request is deprecated; use reveal calls')
    assert err.splitlines()[-1] == f"error: {document['error']}"
