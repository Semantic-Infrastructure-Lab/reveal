"""Out-of-range walk depth is refused everywhere (Scott 2026-11-24, BACK-2793; COMMAND_MODEL "Walk depth range").

``depth`` is graph hops, 1..5, wherever it is declared: calls ``--callers`` and ``--callees`` (and the retired
``--root``), trace, and the element views' ``--transitive``, the legacy ``--boundary``/``--sideeffects``/``--effects
--transitive --depth`` spellings included. A value outside the range is an invalid request: exit 2 with ``depth must
be 1..5, got N`` on the subcommand, the URI, a flag after the URI, a ``--stdin`` line, ``api.query``
(RequestValidationError) and MCP. Other depths are different quantities and keep their own domains (nesting depth,
surface's directory depth).

Before (measured at fccb3bf2): calls and trace clamped silently on every transport (0 and negatives walked one level,
6 or more walked five, exit 0); the legacy element spellings clamped too (``--depth 0`` meant the default 2); and the
clamp hid a conflicting URI/flag pair (``?depth=6 --depth 9`` answered depth 5). Each refusal here sits beside an
in-range sibling that answers; conformance column 31 holds the rule on every noun that declares a depth.
"""
import json

import pytest

from conftest import _run_reveal_in

# main -> f1 -> ... -> f7 -> os.remove: a walk of N hops from either end shows N levels.
CHAIN = 'import os\n\n\ndef main():\n    f1()\n\n\n' + ''.join(
    f'def f{k}():\n    f{k + 1}()\n\n\n' for k in range(1, 7)) + 'def f7():\n    os.remove("x")\n'
OUTSIDE = ('0', '-1', '6')
INSIDE = ('1', '5')


@pytest.fixture
def chain(tmp_path, monkeypatch):
    (tmp_path / 'chain.py').write_text(CHAIN, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _refusal(value):
    return f'depth must be 1..5, got {int(value)}'


def _cli(root, *argv, stdin=None):
    return _run_reveal_in(root, *argv, '--format', 'json', stdin=stdin)


def _refused(result, value):
    text = result.stdout + result.stderr
    return result.returncode == 2 and _refusal(value) in text and 'Traceback' not in text


def _answer(result):
    assert result.returncode == 0, (result.stdout + result.stderr)[:400]
    return json.loads(result.stdout)


# Each CLI form of a declared walk depth: (label, argv for a depth value, or a --stdin line).
CLI_FORMS = {
    'calls --callers subcommand': lambda v: ['calls', '.', '--callers', 'f7', '--depth', v],
    'calls --callers URI': lambda v: [f'calls://.?callers=f7&depth={v}'],
    'calls --callers flag after URI': lambda v: ['calls://.?callers=f7', '--depth', v],
    'calls --callees subcommand': lambda v: ['calls', '.', '--callees', 'main', '--depth', v],
    'calls --callees URI': lambda v: [f'calls://.?callees=main&depth={v}'],
    'calls ?root (retired) URI': lambda v: [f'calls://.?root=main&depth={v}'],
    'trace subcommand': lambda v: ['trace', '.', '--from', 'main', '--depth', v],
    'trace URI': lambda v: [f'trace://.?from=main&depth={v}'],
    'trace flag after URI': lambda v: ['trace://.?from=main', '--depth', v],
}
STDIN_FORMS = {
    'calls --callers --stdin line': lambda v: f'calls . --callers f7 --depth {v}',
    'calls URI --stdin line': lambda v: f'calls://.?callers=f7&depth={v}',
    'trace --stdin line': lambda v: f'trace . --from main --depth {v}',
}
API_FORMS = {
    'calls --callers': ('calls://.?callers=f7', {}),
    'calls --callees': ('calls://.?callees=main', {}),
    'trace': ('trace://.?from=main', {}),
}


@pytest.mark.parametrize('value', OUTSIDE)
@pytest.mark.parametrize('form', sorted(CLI_FORMS))
def test_an_out_of_range_depth_exits_2_naming_the_range(chain, form, value):
    result = _cli(chain, *CLI_FORMS[form](value))
    assert _refused(result, value), f'{form} {value}: exit {result.returncode}: {(result.stdout + result.stderr)[:300]}'


@pytest.mark.parametrize('value', INSIDE)
@pytest.mark.parametrize('form', sorted(CLI_FORMS))
def test_an_in_range_depth_answers_at_that_depth(chain, form, value):
    # a depth-1 callee answer is find_callees' per-definition list, which states no depth
    assert _answer(_cli(chain, *CLI_FORMS[form](value))).get('depth', 1) == int(value)


@pytest.mark.parametrize('value', INSIDE)
def test_the_callers_walk_shows_one_level_per_hop(chain, value):
    answer = _answer(_cli(chain, 'calls', '.', '--callers', 'f7', '--depth', value))
    assert len(answer['levels']) == int(value)


@pytest.mark.parametrize('value', OUTSIDE)
@pytest.mark.parametrize('form', sorted(STDIN_FORMS))
def test_an_out_of_range_depth_on_a_stdin_line_exits_2(chain, form, value):
    result = _run_reveal_in(chain, '--stdin', '--format', 'json', stdin=STDIN_FORMS[form](value) + '\n')
    assert _refused(result, value), f'{form} {value}: exit {result.returncode}: {(result.stdout + result.stderr)[:300]}'


@pytest.mark.parametrize('form', sorted(STDIN_FORMS))
def test_an_in_range_depth_on_a_stdin_line_answers(chain, form):
    result = _run_reveal_in(chain, '--stdin', '--format', 'json', stdin=STDIN_FORMS[form]('5') + '\n')
    assert result.returncode == 0 and '"depth": 5' in result.stdout, (result.stdout + result.stderr)[:400]


@pytest.mark.parametrize('value', OUTSIDE)
@pytest.mark.parametrize('form', sorted(API_FORMS))
def test_api_query_raises_request_validation_error_naming_the_range(chain, form, value):
    from reveal import api
    from reveal.errors import RequestValidationError
    uri, keywords = API_FORMS[form]
    with pytest.raises(RequestValidationError, match=_refusal(value).replace('.', r'\.')):
        api.query(uri, depth=int(value), **keywords)


@pytest.mark.parametrize('value', INSIDE)
@pytest.mark.parametrize('form', sorted(API_FORMS))
def test_api_query_answers_an_in_range_depth(chain, form, value):
    from reveal import api
    uri, keywords = API_FORMS[form]
    assert api.query(uri, depth=int(value), **keywords).get('depth', 1) == int(value)  # callees at 1 state none


def _mcp(call):
    try:
        return call()
    except Exception as exc:  # a raised tool error is the refusal on MCP; its text is the measured outcome
        return f'[reveal error: {exc}]'


MCP_RUN_FORMS = {
    'calls --callers': lambda v: ['calls', '.', '--callers', 'f7', '--depth', v],
    'calls --callees': lambda v: ['calls', '.', '--callees', 'main', '--depth', v],
    'trace': lambda v: ['trace', '.', '--from', 'main', '--depth', v],
    'element --view boundary --transitive': lambda v: ['chain.py', 'main', '--view', 'boundary', '--transitive',
                                                       '--depth', v],
}


@pytest.mark.parametrize('value', OUTSIDE)
@pytest.mark.parametrize('form', sorted(MCP_RUN_FORMS))
def test_mcp_reveal_run_refuses_an_out_of_range_depth(chain, form, value):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    shown = _mcp(lambda: reveal_run([*MCP_RUN_FORMS[form](value), '--format', 'json']))
    assert 'reveal error' in shown and _refusal(value) in shown, shown[:300]


@pytest.mark.parametrize('form', sorted(MCP_RUN_FORMS))
def test_mcp_reveal_run_answers_an_in_range_depth(chain, form):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    shown = _mcp(lambda: reveal_run([*MCP_RUN_FORMS[form]('5'), '--format', 'json']))
    assert 'reveal error' not in shown, shown[:300]
    answer = json.loads(shown)
    assert answer.get('depth', answer.get('meta', {}).get('depth')) == 5, shown[:300]


@pytest.mark.parametrize('value', OUTSIDE)
def test_mcp_reveal_trace_refuses_an_out_of_range_depth(chain, value):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_trace
    shown = _mcp(lambda: reveal_trace('.', 'main', depth=int(value)))
    assert 'reveal error' in shown and _refusal(value) in shown, shown[:300]


def test_mcp_reveal_trace_answers_an_in_range_depth(chain):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_trace
    shown = _mcp(lambda: reveal_trace('.', 'main', depth=5))
    assert 'reveal error' not in shown and '(depth 5)' in shown, shown[:300]


@pytest.mark.parametrize('value', OUTSIDE)
def test_mcp_reveal_nav_refuses_an_out_of_range_depth(chain, value):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_nav
    shown = _mcp(lambda: reveal_nav('chain.py', 'main', 'effects', transitive=True, depth=int(value)))
    assert 'reveal error' in shown and _refusal(value) in shown, shown[:300]


def test_mcp_reveal_nav_answers_an_in_range_depth(chain):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_nav
    shown = _mcp(lambda: reveal_nav('chain.py', 'main', 'effects', transitive=True, depth=5))
    assert 'reveal error' not in shown and 'depth=5' in shown, shown[:300]


# -- the element views: every spelling of --transitive --depth, the legacy ones included (X10 reversed) ---------------

ELEMENT_FORMS = {
    '--view boundary': ['--view', 'boundary', '--transitive'],
    '--view effects': ['--view', 'effects', '--transitive'],
    'legacy --boundary': ['--boundary', '--transitive'],
    'legacy --sideeffects': ['--sideeffects', '--transitive'],
    'legacy --effects': ['--effects', '--transitive'],
}


@pytest.mark.parametrize('value', OUTSIDE)
@pytest.mark.parametrize('form', sorted(ELEMENT_FORMS))
def test_an_out_of_range_transitive_depth_exits_2_on_every_spelling(chain, form, value):
    result = _cli(chain, 'chain.py', 'main', *ELEMENT_FORMS[form], '--depth', value)
    assert _refused(result, value), f'{form} {value}: exit {result.returncode}: {(result.stdout + result.stderr)[:300]}'


@pytest.mark.parametrize('value', INSIDE)
@pytest.mark.parametrize('form', sorted(ELEMENT_FORMS))
def test_an_in_range_transitive_depth_answers_on_every_spelling(chain, form, value):
    answer = _answer(_cli(chain, 'chain.py', 'main', *ELEMENT_FORMS[form], '--depth', value))
    if 'boundary' in form:  # the boundary JSON states the hop budget (meta.depth); the effects JSON states none (B2)
        assert answer['meta']['depth'] == int(value)


@pytest.mark.parametrize('form', ['legacy --boundary', 'legacy --sideeffects'])
def test_the_legacy_transitive_depth_defaults_to_two_only_when_absent(chain, form):
    """``--depth 0`` on the old flags meant the default 2; now only an absent ``--depth`` is the default."""
    absent = _cli(chain, 'chain.py', 'main', *ELEMENT_FORMS[form])
    assert absent.returncode == 0, absent.stderr[:300]
    if 'boundary' in form:
        assert json.loads(absent.stdout)['meta']['depth'] == 2
    assert _refused(_cli(chain, 'chain.py', 'main', *ELEMENT_FORMS[form], '--depth', '0'), '0')


# -- the clamp hid a conflicting URI/flag pair (rule "Conflicting values") ----------------------------------------

@pytest.mark.parametrize('uri,flag', [('calls://.?callers=f7&depth=6', '9'), ('trace://.?from=main&depth=6', '50')])
def test_two_different_out_of_range_depths_conflict(chain, uri, flag):
    result = _cli(chain, uri, '--depth', flag)
    text = result.stdout + result.stderr
    assert result.returncode == 2 and '--depth' in text and 'depth=6' in text and 'conflict' in text, text[:300]


@pytest.mark.parametrize('uri', ['calls://.?callers=f7&depth=3', 'trace://.?from=main&depth=3'])
def test_two_different_in_range_depths_conflict_and_equal_ones_answer(chain, uri):
    conflict = _cli(chain, uri, '--depth', '4')
    assert conflict.returncode == 2 and 'depth=3' in conflict.stdout + conflict.stderr
    assert _answer(_cli(chain, uri, '--depth', '3'))['depth'] == 3


@pytest.mark.parametrize('uri,keyword,refused', [('calls://.?callers=f7&depth=6', 9, 6),
                                                   ('calls://.?callers=f7&depth=6', 2, 6),
                                                   ('calls://.?callers=f7&depth=3', 9, 9)])
def test_api_query_refuses_an_out_of_range_depth_on_either_side_of_an_override(chain, uri, keyword, refused):
    """On api.query a keyword overrides the URI's value (the typed overlay rule); the clamp hid an out-of-range URI
    value (``?depth=6`` with ``depth=9`` answered depth 5). Either out-of-range side is refused now, the URI's first."""
    from reveal import api
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError, match=_refusal(refused).replace('.', r'\.')):
        api.query(uri, depth=keyword)


def test_api_query_answers_an_in_range_override(chain):
    from reveal import api
    assert api.query('calls://.?callers=f7&depth=3', depth=4)['depth'] == 4


# -- other depths are different quantities: their own domains stay (negative controls) ---------------------------

def test_the_nesting_depth_has_no_upper_bound(chain):
    assert _cli(chain, 'chain.py', 'main', '--view', 'flow', '--nesting-depth', '50').returncode == 0


def test_surface_directory_depth_has_no_upper_bound(chain):
    assert _cli(chain, 'surface', '.', '--view', 'dir', '--dir-depth', '99').returncode == 0


def test_a_directory_tree_depth_is_not_a_walk_depth(chain):
    assert _run_reveal_in(chain, '.', '--depth', '9').returncode == 0
