"""Typed effects controls cross direct, registered SDK and actual stdio boundaries."""
import asyncio

import pytest

pytest.importorskip('mcp')
from mcp.types import CallToolRequestParams

from conftest import _run_reveal_direct
from test_effects_activation_back2461 import project
from test_mcp_expected_errors_back1992 import _run as _stdio, _text

pytestmark = [pytest.mark.mcp, pytest.mark.component]

CASES = [({}, ()), ({'mode': 'ordinary'}, ()), ({'mode': 'loops'}, ('--in-loops',)),
         ({'mode': 'state'}, ('--state',)), ({'transitive': True}, ('--transitive',)),
         ({'transitive': True, 'depth': 1}, ('--transitive', '--depth', '1')),
         ({'mode': 'loops', 'depth': 8}, ('--in-loops', '--depth', '8'))]
INVALID = [{'mode': 'unknown'}, {'mode': 'loops', 'transitive': True},
           {'mode': 'state', 'depth': 2}, {'depth': 2},
           *({'transitive': True, 'depth': value} for value in (0, -1, 6, True, '2', 2.0)),
           *({'transitive': value} for value in ('false', 'yes', 1, 0)),
           {'flag_value': '--transitive'}, {'mode': 'loops,state'}, {'mode': ['loops', 'state']}]


def _arguments(project, controls):
    return {'path': str(project), 'element': 'entry', 'flag': 'effects', **controls}


def _sdk(arguments):
    from reveal.mcp_server import mcp

    async def call():
        return await mcp._handle_call_tool(None, CallToolRequestParams(name='reveal_nav', arguments=arguments))
    return asyncio.run(call())


@pytest.mark.parametrize('controls,flags', CASES)
def test_direct_and_registered_sdk_match_cli_text(project, controls, flags):
    from reveal.mcp_server import reveal_nav

    expected = _run_reveal_direct(str(project), 'entry', '--effects', *flags)
    assert expected.returncode == 0, expected.stderr
    direct = reveal_nav(**_arguments(project, controls))
    assert direct.rstrip() == expected.stdout.rstrip()
    answer = _sdk(_arguments(project, controls))
    assert not answer.is_error, _text(answer)
    assert _text(answer).rstrip() == expected.stdout.rstrip()


@pytest.mark.parametrize('controls', INVALID)
def test_invalid_typed_requests_are_authored_sdk_errors(project, controls):
    answer = _sdk(_arguments(project, controls))
    assert answer.is_error, _text(answer)
    assert 'Traceback' not in _text(answer) and 'internal error' not in _text(answer).lower()


@pytest.mark.parametrize('controls', [{'mode': 'ordinary'}, {'transitive': True}, {'depth': 1}])
def test_controls_on_other_flags_are_errors(project, controls):
    answer = _sdk({**_arguments(project, controls), 'flag': 'boundary'})
    assert answer.is_error, _text(answer)
    assert 'effects' in _text(answer)


@pytest.mark.parametrize('controls', [{'depth': True}, {'depth': '2'}, {'depth': 2.0}, {'transitive': 1}, {'transitive': 0}, {'transitive': 'false'}, {'mode': ['loops', 'state']}])
def test_direct_calls_also_validate_exact_types(project, controls):
    from reveal.mcp_server import reveal_nav

    result = reveal_nav(**_arguments(project, controls))
    assert '[reveal error:' in result


def test_mcp_invocation_records_only_controls_actually_supplied(project, monkeypatch):
    from reveal.mcp_server import reveal_nav
    from reveal.cli.invocation import current_invocation
    import reveal.file_handler as file_handler

    real_handle = file_handler.handle_file
    invocations = []

    def handle(*args, **kwargs):
        invocations.append(current_invocation().argv)
        return real_handle(*args, **kwargs)

    monkeypatch.setattr(file_handler, 'handle_file', handle)
    for controls, flags in CASES:
        result = reveal_nav(**_arguments(project, controls))
        assert '[reveal error:' not in result
        assert invocations[-1] == ('--effects', *flags, '--', str(project), 'entry')


def test_legacy_mcp_defaults_keep_answer_and_add_only_correction(project):
    from reveal.mcp_server import reveal_nav

    for old, mode in [('sideeffects', 'ordinary'), ('fanout', 'loops'), ('statewrites', 'state')]:
        old_text = reveal_nav(str(project), 'entry', old)
        new_text = reveal_nav(str(project), 'entry', 'effects', mode=mode)
        assert old_text.startswith(new_text.rstrip())
        assert old_text.count('deprecated') == 1
        registered = _sdk({'path': str(project), 'element': 'entry', 'flag': old})
        assert not registered.is_error and _text(registered).rstrip() == old_text.rstrip()


def test_stdio_valid_modes_strict_errors_and_sibling_recovery(tmp_path, project):
    async def scenario(session):
        legacy = await session.call_tool('reveal_nav', {'path': str(project), 'element': 'entry', 'flag': 'sideeffects'})
        assert not legacy.is_error and _text(legacy).count('deprecated') == 1
        for controls, flags in CASES:
            answer = await session.call_tool('reveal_nav', _arguments(project, controls))
            assert not answer.is_error, _text(answer)
            assert 'deprecated' not in _text(answer)
            expected = _run_reveal_direct(str(project), 'entry', '--effects', *flags)
            assert _text(answer).rstrip() == expected.stdout.rstrip()
        for controls in INVALID:
            answer = await session.call_tool('reveal_nav', _arguments(project, controls))
            assert answer.is_error, (controls, _text(answer))
        other = await session.call_tool('reveal_nav', {**_arguments(project, {'depth': 1}), 'flag': 'boundary'})
        assert other.is_error
        recovered = await session.call_tool('reveal_nav', _arguments(project, {}))
        assert not recovered.is_error
        line = await session.call_tool('reveal_nav', {**_arguments(project, {}), 'element': ':6-10'})
        assert not line.is_error
        unrelated = await session.call_tool('reveal_nav', {'path': str(project), 'element': 'entry', 'flag': 'varflow', 'flag_value': 'items'})
        assert not unrelated.is_error and 'deprecated' not in _text(unrelated)
    _stdio(tmp_path, scenario)


def test_registered_schema_preserves_positional_fields_and_adds_typed_controls():
    from reveal.mcp_server import mcp

    tools = asyncio.run(mcp.list_tools())
    tool = next(tool for tool in tools if tool.name == 'reveal_nav')
    schema = tool.input_schema
    assert schema['required'] == ['path', 'element', 'flag']
    properties = schema['properties']
    assert properties['flag_value']['default'] == ''
    assert properties['mode']['default'] is None
    assert properties['mode']['anyOf'] == [{'enum': ['ordinary', 'loops', 'state'], 'type': 'string'}, {'type': 'null'}]
    assert properties['transitive']['type'] == 'boolean' and properties['transitive']['default'] is False
    assert properties['depth']['default'] is None
    assert properties['depth']['anyOf'] == [{'type': 'integer'}, {'type': 'null'}]


def test_registered_effects_rejects_directory_as_authored_request_error(project):
    answer = _sdk({**_arguments(project, {}), 'path': str(project.parent)})
    assert answer.is_error and 'code file' in _text(answer)
