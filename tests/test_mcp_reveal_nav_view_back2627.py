"""MCP ``reveal_nav`` is ``reveal PATH ELEMENT --view VIEW`` (BACK-2627 X13, D20/D21; B5).

The tool mapped its controls itself, beside the CLI parser: it had no ``view`` parameter (the view travelled in
``flag``), split ``flow``'s comma form into kinds without the note the CLI's ``--flow=if,try`` gives, and named an
absolute ``REVEAL_CONFIG`` path where the CLI names the spelling (B5). Now it builds the CLI's command line and runs it
through the CLI's dispatch, as ``reveal_element`` and ``reveal_run`` do: its typed parameters are the element views'
declarations (``mode`` stays the MCP spelling of ``--in-loops``/``--state``, D10), ``flag``/``flag_value`` spell the
CLI's own flag with that flag's note, and every value, conflict, depth range and config failure is the CLI's.

Each answer is compared with ``reveal_run`` over the same command line (the MCP transport's CLI tool; D21: equal answer
and outcome), through a registered SDK call. Siblings that answered before and still do: the positional ``flag`` form
of a word with a note (``sideeffects``), an operation (``varflow``) and the unknown-flag refusal.
"""
import asyncio
import os

import pytest

pytest.importorskip('mcp')
from mcp.types import CallToolRequestParams

from reveal import mcp_server
from test_mcp_expected_errors_back1992 import _text

pytestmark = [pytest.mark.mcp, pytest.mark.component]

SOURCE = ('import os\n\n\ndef f(x, items):\n    total = 0\n    for i in items:\n        if i > x:\n'
          '            try:\n                total += os.path.getsize(i)\n            except OSError:\n'
          '                pass\n    return total\n')


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'a.py').write_text(SOURCE, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    return tmp_path


def _sdk(arguments):
    async def call():
        return await mcp_server.mcp._handle_call_tool(None, CallToolRequestParams(name='reveal_nav', arguments=arguments))
    return asyncio.run(call())


def _cli(*flags):
    """What ``reveal a.py f FLAGS`` answers through the MCP transport's command-line tool."""
    return mcp_server.reveal_run(['--format', 'text', *flags, '--', 'a.py', 'f'])


def _refusal(cli_text):
    """The CLI's refusal text inside reveal_run's tool error."""
    assert isinstance(cli_text, mcp_server._ToolFailure), cli_text
    return cli_text.removeprefix('[reveal error: ').removesuffix(']')


CANONICAL = [
    ({'view': 'boundary'}, ('--view', 'boundary')),
    ({'view': 'flow', 'kind': ['if', 'try']}, ('--view', 'flow', '--kind', 'if', '--kind', 'try')),
    ({'view': 'effects', 'mode': 'loops', 'nesting_depth': 2}, ('--view', 'effects', '--in-loops', '--nesting-depth', '2')),
    ({'view': 'effects', 'transitive': True, 'depth': 1}, ('--view', 'effects', '--transitive', '--depth', '1')),
    ({'view': 'exits', 'range': '5-12'}, ('--view', 'exits', '--range', '5-12')),
]


@pytest.mark.parametrize('controls, flags', CANONICAL)
def test_a_typed_view_answers_as_the_cli(fx, controls, flags):
    expected = _cli(*flags)
    assert not isinstance(expected, mcp_server._ToolFailure), expected
    answer = _sdk({'path': 'a.py', 'element': 'f', **controls})
    assert not answer.is_error, _text(answer)
    assert _text(answer) == expected
    assert 'deprecated' not in _text(answer)
    assert mcp_server.reveal_nav('a.py', 'f', **controls) == expected  # a direct call is the same request


@pytest.mark.parametrize('controls, flags', [
    ({'view': 'flow', 'kind': ['if,try']}, ('--view', 'flow', '--kind', 'if,try')),  # one union syntax: repeat
    ({'flag': 'boundary', 'view': 'flow'}, ('--boundary', '--view', 'flow')),  # two spellings of one control
    ({'view': 'effects', 'transitive': True, 'depth': 9}, ('--view', 'effects', '--transitive', '--depth', '9')),
    ({'view': 'nope'}, ('--view', 'nope')),
    ({'view': 'boundary', 'depth': 1}, ('--view', 'boundary', '--depth', '1')),  # depth needs --transitive
])
def test_an_invalid_request_is_the_clis_refusal(fx, controls, flags):
    refusal = _refusal(_cli(*flags))
    answer = _sdk({'path': 'a.py', 'element': 'f', **controls})
    assert answer.is_error and refusal in _text(answer), _text(answer)


@pytest.mark.parametrize('flag, flag_value, controls, flags', [
    ('flow', 'if,try', {}, ('--flow=if,try',)),  # the legacy comma union, noted as the CLI notes it
    ('boundary', '', {}, ('--boundary',)),  # a view word in flag is the CLI's legacy flag, with its row's note
    ('effects', '', {'mode': 'loops', 'depth': 8}, ('--effects', '--in-loops', '--depth', '8')),  # D10's call keeps its answer
])
def test_a_legacy_flag_is_the_clis_flag_with_its_note(fx, flag, flag_value, controls, flags):
    expected = _cli(*flags)
    assert not isinstance(expected, mcp_server._ToolFailure) and expected.count('deprecated') == 1, expected
    answer = _sdk({'path': 'a.py', 'element': 'f', 'flag': flag, 'flag_value': flag_value, **controls})
    assert not answer.is_error, _text(answer)
    assert _text(answer) == expected


@pytest.mark.parametrize('flag, flag_value, flags', [
    ('sideeffects', '', ('--sideeffects',)),
    ('varflow', 'total', ('--varflow=total',)),
])
def test_sibling_a_positional_flag_still_answers_as_the_cli(fx, flag, flag_value, flags):
    answer = _sdk({'path': 'a.py', 'element': 'f', 'flag': flag, 'flag_value': flag_value})
    assert not answer.is_error, _text(answer)
    assert _text(answer) == _cli(*flags)


def test_sibling_an_unknown_flag_is_still_refused(fx):
    answer = _sdk({'path': 'a.py', 'element': 'f', 'flag': 'notaflag'})
    assert answer.is_error and "unknown nav flag 'notaflag'" in _text(answer)


def test_a_missing_reveal_config_is_named_as_spelled(fx, monkeypatch):
    """B5: the CLI and reveal_element name the REVEAL_CONFIG value as given; reveal_nav named the absolute path."""
    monkeypatch.setenv('REVEAL_CONFIG', os.path.join('nosuch', 'reveal.yaml'))
    expected = _cli('--boundary')
    assert isinstance(expected, mcp_server._ToolFailure)
    answer = _sdk({'path': 'a.py', 'element': 'f', 'flag': 'boundary'})
    assert answer.is_error and _refusal(expected) in _text(answer), _text(answer)
    assert os.fspath(fx) not in _text(answer) and os.fspath(fx.resolve()) not in _text(answer)


def test_the_schema_is_the_element_view_declarations():
    """Every typed control is a declared element-view control (the view and what the views read), named with - as _,
    typed and described by its declaration; mode is D10's spelling of the two effects switches."""
    from reveal import nav_params

    mode_switches = {nav_params.IN_LOOPS.name, nav_params.STATE.name}
    declared = [spec for spec in nav_params.ELEMENT_VIEW_SPECS if spec.name not in mode_switches and (
        spec is nav_params.VIEW or any(a == 'view' or a.startswith('view=') for a in spec.answers))]
    assert {spec.name for spec in declared} == {'view', 'kind', 'transitive', 'depth', 'nesting-depth', 'range'}
    tools = asyncio.run(mcp_server.mcp.list_tools())
    schema = next(tool for tool in tools if tool.name == 'reveal_nav').input_schema
    assert schema['required'] == ['path', 'element']
    properties = schema['properties']
    assert set(properties) == {'path', 'element', 'flag', 'flag_value', 'mode', *(s.name.replace('-', '_') for s in declared)}
    for spec in declared:
        prop = properties[spec.name.replace('-', '_')]
        assert prop['description'] == spec.description
        kinds = [branch.get('type') for branch in prop.get('anyOf', [prop])]
        want = 'array' if spec.repeatable else spec.type
        assert want in kinds, (spec.name, prop)
        assert prop['default'] == (False if spec.type == 'boolean' else None)
