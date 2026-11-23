"""The main parser raises its usage errors when asked (BACK-2325, D21): ``raise_usage_errors`` lives on
``JsonUsageParser``, the one seam both the main parser and every noun's declared parser derive from, so the Python API
reads a path read's request with the CLI's own parser and gets the CLI's message as a ``RequestValidationError``;
nothing prints and nothing exits, as the noun form already does with the declared parser (BACK-2717).

Shared owners: ``cli/routing/declared.py`` (``JsonUsageParser``) and ``cli/parser.py`` (``_ScopedErrorArgumentParser``).
Effect on every noun and transport: none unless a caller sets the attribute (only the API does); the CLI's text and JSON
usage errors are unchanged (controls below), and the declared parser raises exactly as before.
"""
import pytest

from reveal import __version__
from reveal.cli.parser import create_argument_parser
from reveal.cli.routing.declared import create_declared_parser
from reveal.errors import RequestValidationError

pytestmark = [pytest.mark.unit]


def _raising_parser():
    parser = create_argument_parser(__version__)
    parser.raise_usage_errors = True
    return parser


@pytest.mark.parametrize('argv,message', [
    (['--head', 'x', 'ok.py'], "argument --head: invalid int value: 'x'"),
    (['ok.py', '--zz'], 'unrecognized arguments: --zz'),
    (['ok.py', '--format', 'yaml'], "argument --format: invalid choice: 'yaml'"),
])
def test_the_main_parser_raises_the_message_the_cli_prints(capsys, argv, message):
    with pytest.raises(RequestValidationError) as raised:
        _raising_parser().parse_args(argv)
    assert str(raised.value).startswith(message)
    assert capsys.readouterr() == ('', '')


def test_a_taught_message_is_the_one_raised(capsys):
    # An element view request of a path read names its declarations for an unknown flag (BACK-2756): that message, not
    # argparse's, is what the CLI prints after 'error: ', so it is what the API gets.
    with pytest.raises(SystemExit):
        create_argument_parser(__version__).parse_args(['ok.py', 'foo', '--view', 'boundary', '--zz'])
    printed = capsys.readouterr().err
    with pytest.raises(RequestValidationError) as raised:
        _raising_parser().parse_args(['ok.py', 'foo', '--view', 'boundary', '--zz'])
    assert capsys.readouterr() == ('', '')
    assert f': error: {raised.value}\n' in printed
    assert 'unrecognized arguments' not in str(raised.value)


def test_the_cli_parser_still_prints_and_exits_2(capsys):
    # Negative control: the attribute defaults to False on the main parser; the CLI's text error is unchanged.
    parser = create_argument_parser(__version__)
    assert getattr(parser, 'raise_usage_errors', False) is False
    with pytest.raises(SystemExit) as exited:
        parser.parse_args(['--head', 'x', 'ok.py'])
    assert exited.value.code == 2
    assert ": error: argument --head: invalid int value: 'x'" in capsys.readouterr().err


def test_the_declared_parser_raises_as_before(capsys):
    # Sibling: the noun form's parser (BACK-2717) keeps its behaviour.
    parser = create_declared_parser('ast')
    parser.raise_usage_errors = True
    with pytest.raises(RequestValidationError) as raised:
        parser.parse_args(['.', '--zz'])
    assert '--zz' in str(raised.value)
    assert capsys.readouterr() == ('', '')
