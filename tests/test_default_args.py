"""cli/defaults.py::_default_args must be derived from the parser, not a hand-kept copy.

The hand-written dict had drifted: 36 parser dests missing, and `depth` defaulting to 3
where the parser says None -- which made every internal caller (MCP reveal_query, tests)
print a false "--depth has no effect on <scheme>://" note. BACK-1362.
"""
import io
from contextlib import redirect_stderr

import pytest

from reveal.cli.defaults import _default_args
from reveal.cli.parser import create_argument_parser


def _parser_defaults():
    return vars(create_argument_parser('0', full_help=False).parse_args([]))


def test_every_parser_dest_is_present_with_the_parser_default():
    got = vars(_default_args())
    for dest, default in _parser_defaults().items():
        assert dest in got, f'--{dest} missing from _default_args()'
        assert got[dest] == default, f'{dest}: _default_args()={got[dest]!r}, parser={default!r}'


def test_pack_only_extras_survive():
    args = _default_args()
    assert (args.content, args.focus, args.budget) == (False, None, '2000')


def test_overrides_win_and_unknown_overrides_are_kept():
    args = _default_args(format='json', targets=['a'])
    assert args.format == 'json' and args.targets == ['a']


def test_each_call_returns_an_independent_namespace():
    first = _default_args()
    first.exclude = ['x']
    first.extra_state = True
    second = _default_args()
    assert second.exclude is None and not hasattr(second, 'extra_state')


def test_reveal_format_is_read_per_call_not_frozen_by_the_cache(monkeypatch):
    """The parser defaults are cached per process; REVEAL_FORMAT must not be. A first
    call made under REVEAL_FORMAT=json turned every later call's format to json, so
    MCP tools and handle_uri emitted JSON -- 14 tests failed on one xdist worker."""
    from reveal.cli.defaults import _parser_defaults as cached
    cached.cache_clear()
    monkeypatch.setenv('REVEAL_FORMAT', 'json')
    assert _default_args().format == 'json'
    monkeypatch.delenv('REVEAL_FORMAT')
    assert _default_args().format == 'text'


@pytest.mark.parametrize('scheme', ['ast', 'calls', 'git', 'markdown'])
def test_default_args_do_not_trigger_the_structural_flag_warning(scheme):
    from reveal.cli.routing.uri import _warn_unsupported_structural_flags

    err = io.StringIO()
    with redirect_stderr(err):
        _warn_unsupported_structural_flags('x', scheme, _default_args())
    assert err.getvalue() == ''
