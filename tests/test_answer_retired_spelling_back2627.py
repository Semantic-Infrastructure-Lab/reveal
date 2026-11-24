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
