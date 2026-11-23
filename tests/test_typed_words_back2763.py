"""A value flag typed without its value does not swallow ``--format json`` (BACK-2763).

``JsonUsageParser`` is the one JSON-usage seam of the main parser and of every declared noun's parser: a usage error in a
request that asks for JSON answers with the invalid-request document. When argparse's own error stops the tolerant
re-read (``--limit`` missing its value), the request's format is recovered from the typed words. ``_typed_words`` took
the next word as the missing value even when it was an option string, so ``reveal ast proj --limit --format json``
read ``--format`` as the limit, lost JSON mode, and answered argparse's text usage with empty stdout. argparse never
takes an option string as a value ("expected one argument"); the typed words now read the request as argparse does.

Effect on every noun: one seam, so every declared noun's parser (subcommand and URI) and the main parser recover JSON
mode for "a value flag missing its value, followed by ``--format json``". Requests whose value comes last, explicit
``--flag=VALUE`` spellings, a negative number value and text mode are unchanged (controls below).
"""
import json

import pytest

from reveal.cli.routing.declared import JsonUsageParser
from test_vocabulary_conformance_back2654 import _invalid_document, _run, workspace  # noqa: F401  (the fixture)


def _parser():
    parser = JsonUsageParser(prog='reveal-demo')
    parser.add_argument('path', nargs='?')
    parser.add_argument('--limit')
    parser.add_argument('--format')
    parser.add_argument('--verbose', action='store_true')
    return parser


def _typed(argv):
    parser = _parser()
    parser._argv = list(argv)
    return parser._typed_words()


# argv -> (positionals, values) as argparse reads the words
TYPED = [
    # an option string is never a missing option's value
    (['proj', '--limit', '--format', 'json'], (['proj'], {'limit': [''], 'format': ['json']})),
    (['proj', '--limit', '--verbose', '--format', 'json'], (['proj'], {'limit': [''], 'verbose': [''], 'format': ['json']})),
    # an unknown option word is not a value either (argparse: "expected one argument")
    (['proj', '--limit', '--zz', '--format', 'json'], (['proj'], {'limit': [''], 'format': ['json']})),
    (['proj', '--limit'], (['proj'], {'limit': ['']})),
    # controls: what argparse does read as a value stays a value
    (['proj', '--limit', '5', '--format', 'json'], (['proj'], {'limit': ['5'], 'format': ['json']})),
    (['proj', '--limit', '-1', '--format', 'json'], (['proj'], {'limit': ['-1'], 'format': ['json']})),
    (['proj', '--limit', '-', '--format', 'json'], (['proj'], {'limit': ['-'], 'format': ['json']})),
    (['proj', '--limit=--format', 'json'], (['proj', 'json'], {'limit': ['--format']})),
    (['--', '--limit', '--format'], (['--limit', '--format'], {})),
]


@pytest.mark.parametrize('argv, expected', TYPED, ids=[' '.join(argv) for argv, _expected in TYPED])
def test_typed_words_read_values_as_argparse_does(argv, expected):
    assert _typed(argv) == expected


@pytest.mark.parametrize('argv', [argv for argv, _expected in TYPED if '--' not in argv and '--zz' not in argv])
def test_typed_words_agree_with_argparse_where_it_parses(argv):
    """The oracle: wherever argparse itself reads the request, the typed words read the same values."""
    try:
        parsed = _parser().parse_args(argv)
    except SystemExit:
        pytest.skip('argparse refuses this request (a missing value): the typed words are the only reading')
    positionals, values = _typed(argv)
    assert parsed.limit == (values.get('limit') or [None])[-1]
    assert parsed.format == (values.get('format') or [None])[-1]


# (argv, the flag the document names): a value flag missing its value, then --format json
MISSING_VALUE = [
    (('ast', 'proj', '--limit', '--format', 'json'), '--limit'),
    (('ast://proj', '--limit', '--format', 'json'), '--limit'),
    (('json', 'proj/rows.json', '--limit', '--format', 'json'), '--limit'),
    (('markdown', 'proj', '--limit', '--format', 'json'), '--limit'),
]


@pytest.mark.parametrize('argv, flag', MISSING_VALUE, ids=[' '.join(argv) for argv, _flag in MISSING_VALUE])
def test_a_missing_value_before_format_json_answers_the_document(workspace, argv, flag):
    run = _run(*argv)
    assert _invalid_document(run, flag), run.brief()
    assert 'usage:' not in run.err


def test_the_value_last_request_is_unchanged(workspace):
    """Control: the value flag last already answered the document."""
    run = _run('ast', 'proj', '--format', 'json', '--limit')
    assert _invalid_document(run, '--limit'), run.brief()


def test_text_mode_keeps_the_usage_error(workspace):
    """Control: a request that does not ask for JSON keeps argparse's usage error, empty stdout."""
    run = _run('ast', 'proj', '--limit')
    assert run.rc == 2 and run.out == '' and 'expected one argument' in run.err


def test_a_negative_number_value_is_still_read_as_the_value(workspace):
    """Control: argparse reads ``-1`` as the value; the document names the value's own refusal."""
    run = _run('ast', 'proj', '--limit', '-1', '--format', 'json')
    doc = json.loads(run.out)
    assert run.rc == 2 and 'limit must be >= 0' in doc['error']
