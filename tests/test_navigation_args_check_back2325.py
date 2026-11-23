"""The path read's navigation check, raised (BACK-2325, D21): ``check_navigation_args`` is the one check of --head,
--tail, --range, --limit and the element views' variable names; ``validate_navigation_args`` (the CLI, ``main._prepare``)
prints its error and exits 2, and the Python API raises it as a ``RequestValidationError``.

Shared owner: ``cli/parser.py``. Effect on every route and transport: none; the CLI's text and exit are byte-identical
(each case below pins the exact stderr the CLI printed at d080af4f), and an element view's empty variable still raises
``NavRequestValidationError`` to its owner.
"""
import argparse

import pytest

from reveal.cli.parser import check_navigation_args, validate_navigation_args
from reveal.errors import NavRequestValidationError, RequestValidationError

pytestmark = [pytest.mark.unit]

_RANGE_HINT = 'Expected format: START-END or START- for open-ended (e.g., 10-20, 300-, 1-indexed)'


def _args(**given):
    values = {'head': None, 'tail': None, 'range': None, 'limit': None, 'varflow': None, 'keys': None, 'narrow': None}
    values.update(given)
    return argparse.Namespace(**values)


# (given, the CLI's stderr at d080af4f)
_REFUSED = [
    ({'head': 1, 'tail': 1}, 'Error: --head, --tail, and --range are mutually exclusive\n'),
    ({'tail': 2, 'range': '1-2'}, 'Error: --head, --tail, and --range are mutually exclusive\n'),
    ({'head': -1}, 'Error: --head must be 0 or more, got -1\n'),
    ({'tail': -2}, 'Error: --tail must be 0 or more, got -2\n'),
    ({'limit': -3}, 'Error: --limit must be 0 or more, got -3\n'),
    ({'range': 'zz'}, "Error: Invalid range format 'zz': range must be START-END or START- (1-indexed, e.g. 10-20 or "
                      "300-), got 'zz'\n"
                      f'{_RANGE_HINT}\n'),
    ({'range': '9-3'}, "Error: Invalid range format '9-3': Range start must be <= end\n"
                       f'{_RANGE_HINT}\n'),
]


@pytest.mark.parametrize('given,stderr', _REFUSED)
def test_the_check_raises_the_text_the_cli_prints(capsys, given, stderr):
    with pytest.raises(RequestValidationError) as raised:
        check_navigation_args(_args(**given))
    assert not isinstance(raised.value, NavRequestValidationError)
    assert f'Error: {raised.value}\n' == stderr
    assert capsys.readouterr() == ('', '')


@pytest.mark.parametrize('given,stderr', _REFUSED)
def test_the_cli_prints_the_same_text_and_exits_2(capsys, given, stderr):
    with pytest.raises(SystemExit) as exited:
        validate_navigation_args(_args(**given))
    assert exited.value.code == 2
    assert capsys.readouterr() == ('', stderr)


@pytest.mark.parametrize('option', ['varflow', 'keys', 'narrow'])
@pytest.mark.parametrize('check', [check_navigation_args, validate_navigation_args])
def test_an_empty_view_variable_raises_to_its_owner_on_both(capsys, option, check):
    with pytest.raises(NavRequestValidationError, match=f'--{option} takes a variable name'):
        check(_args(**{option: ''}))
    assert capsys.readouterr() == ('', '')


@pytest.mark.parametrize('check', [check_navigation_args, validate_navigation_args])
def test_a_valid_request_passes_and_the_range_is_stored_parsed(capsys, check):
    # Negative control: a valid request is unchanged by either reader, except the range parsed once.
    args = _args(range='2-4', limit=0)
    check(args)
    assert args.range == (2, 4) and args.limit == 0
    head = _args(head=0)
    check(head)
    assert head.head == 0 and head.range is None
    assert capsys.readouterr() == ('', '')
